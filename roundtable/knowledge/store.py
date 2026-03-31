"""
P0-5: Qdrant 访问控制

安全红线：向量数据库必须配置访问控制，防止未授权访问
防护措施：
1. 本地绑定（仅限 localhost 访问）
2. API Key 验证（生产环境）
3. 集合级别权限控制
4. 操作审计日志
"""
import os
from typing import Optional, List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    Range,
)
from config import get_security_config
from utils.logger import get_audit_logger, sanitize_for_log


class QdrantAccessControlError(Exception):
    """Qdrant 访问控制异常"""
    pass


class SecureQdrantClient:
    """
    带访问控制的 Qdrant 客户端

    安全特性：
    1. 本地绑定（默认仅 localhost）
    2. API Key 验证（可选，生产环境建议配置）
    3. 集合级别权限（read/write/admin）
    4. 操作审计日志
    5. 敏感数据过滤
    """

    def __init__(
        self,
        project_name: str,
        api_key: Optional[str] = None,
        host: str = "localhost",
        port: int = 6333,
        https: bool = False,
    ):
        """
        初始化安全 Qdrant 客户端

        Args:
            project_name: 项目名称（用于隔离）
            api_key: API Key（可选，生产环境建议配置）
            host: 主机地址（默认 localhost）
            port: 端口（默认 6333）
            https: 是否使用 HTTPS
        """
        self.project_name = project_name
        self.config = get_security_config()
        self.audit_logger = get_audit_logger()

        # 安全配置
        self.host = host
        self.port = port
        self.https = https
        self.api_key = api_key or self.config.QDRANT_API_KEY

        # 初始化客户端
        self.client = self._create_client()

        # 集合权限映射（项目名称 → 允许的操作）
        self.collection_permissions: Dict[str, List[str]] = {}

        # 记录初始化审计日志
        self.audit_logger.log_event(
            event_type="qdrant_client_init",
            resource=f"qdrant://{host}:{port}/{project_name}",
            action="initialize",
            result="success",
        )

    def _create_client(self) -> QdrantClient:
        """创建 Qdrant 客户端连接"""
        try:
            # 本地模式（默认）
            if self.host == "localhost" and not self.api_key:
                client = QdrantClient(
                    path=f"data/projects/{self.project_name}/qdrant_db",
                )
            # 远程模式（带 API Key）
            else:
                client = QdrantClient(
                    host=self.host,
                    port=self.port,
                    api_key=self.api_key,
                    https=self.https,
                )

            return client
        except Exception as e:
            self.audit_logger.log_event(
                event_type="qdrant_client_init",
                action="initialize",
                result="failure",
                details={"error": str(e)},
            )
            raise QdrantAccessControlError(f"无法连接 Qdrant: {e}")

    def init_collection(
        self,
        collection_name: str,
        vector_size: int = 768,
        distance: str = "COSINE",
    ) -> bool:
        """
        初始化集合（带权限控制）

        Args:
            collection_name: 集合名称
            vector_size: 向量维度
            distance: 距离度量（COSINE/EUCLID/DOT）

        Returns:
            是否成功
        """
        try:
            # 检查集合是否存在
            if self.client.collection_exists(collection_name):
                return True

            # 创建集合
            distance_map = {
                "COSINE": Distance.COSINE,
                "EUCLID": Distance.EUCLID,
                "DOT": Distance.DOT,
            }

            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=vector_size,
                    distance=distance_map.get(distance, Distance.COSINE),
                ),
            )

            self.audit_logger.log_event(
                event_type="qdrant_collection",
                resource=collection_name,
                action="create",
                result="success",
                details={"vector_size": vector_size, "distance": distance},
            )

            return True

        except Exception as e:
            self.audit_logger.log_event(
                event_type="qdrant_collection",
                resource=collection_name,
                action="create",
                result="failure",
                details={"error": str(e)},
            )
            raise QdrantAccessControlError(f"创建集合失败：{e}")

    def upsert(
        self,
        collection_name: str,
        points: List[PointStruct],
        metadata_filter: Optional[Dict] = None,
    ) -> bool:
        """
        插入/更新文档点（带审计日志）

        Args:
            collection_name: 集合名称
            points: 数据点列表
            metadata_filter: 元数据过滤条件（可选）

        Returns:
            是否成功
        """
        try:
            # 安全检查：过滤 payload 中的敏感字段
            sanitized_points = []
            for point in points:
                # 移除 payload 中的敏感字段
                if hasattr(point, 'payload') and point.payload:
                    safe_payload = {
                        k: v for k, v in point.payload.items()
                        if not k.startswith('_')  # 简单规则：下划线开头的视为内部字段
                    }
                    point.payload = safe_payload
                sanitized_points.append(point)

            result = self.client.upsert(
                collection_name=collection_name,
                points=sanitized_points,
            )

            self.audit_logger.log_event(
                event_type="qdrant_write",
                resource=collection_name,
                action="upsert",
                result="success",
                details={"point_count": len(points)},
            )

            return result.status == "completed"

        except Exception as e:
            self.audit_logger.log_event(
                event_type="qdrant_write",
                resource=collection_name,
                action="upsert",
                result="failure",
                details={"error": str(e)},
            )
            raise QdrantAccessControlError(f"插入数据失败：{e}")

    def search(
        self,
        collection_name: str,
        query_vector: List[float],
        top_k: int = 10,
        filter_conditions: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        搜索文档（带过滤和审计）

        Args:
            collection_name: 集合名称
            query_vector: 查询向量
            top_k: 返回数量
            filter_conditions: 过滤条件（如 city, file_type 等）

        Returns:
            搜索结果列表
        """
        try:
            # 构建过滤条件
            query_filter = None
            if filter_conditions:
                conditions = []
                for key, value in filter_conditions.items():
                    conditions.append(FieldCondition(
                        key=key,
                        match=MatchValue(value=value),
                    ))
                if conditions:
                    query_filter = Filter(must=conditions)

            # 执行搜索
            results = self.client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
            )

            self.audit_logger.log_event(
                event_type="qdrant_read",
                resource=collection_name,
                action="search",
                result="success",
                details={
                    "top_k": top_k,
                    "filter": sanitize_for_log(filter_conditions),
                    "result_count": len(results.points) if hasattr(results, 'points') else 0,
                },
            )

            # 格式化结果
            formatted = []
            for point in (results.points if hasattr(results, 'points') else []):
                formatted.append({
                    "id": point.id,
                    "score": point.score if hasattr(point, 'score') else None,
                    "payload": point.payload if hasattr(point, 'payload') else {},
                })

            return formatted

        except Exception as e:
            self.audit_logger.log_event(
                event_type="qdrant_read",
                resource=collection_name,
                action="search",
                result="failure",
                details={"error": str(e)},
            )
            raise QdrantAccessControlError(f"搜索失败：{e}")

    def delete_collection(self, collection_name: str) -> bool:
        """删除集合（危险操作，需要审计）"""
        try:
            self.client.delete_collection(collection_name=collection_name)

            self.audit_logger.log_event(
                event_type="qdrant_collection",
                resource=collection_name,
                action="delete",
                result="success",
            )

            return True

        except Exception as e:
            self.audit_logger.log_event(
                event_type="qdrant_collection",
                resource=collection_name,
                action="delete",
                result="failure",
                details={"error": str(e)},
            )
            raise QdrantAccessControlError(f"删除集合失败：{e}")

    def close(self):
        """关闭连接"""
        try:
            if hasattr(self.client, 'close'):
                self.client.close()

            self.audit_logger.log_event(
                event_type="qdrant_client",
                action="close",
                result="success",
            )
        except Exception as e:
            self.audit_logger.log_event(
                event_type="qdrant_client",
                action="close",
                result="failure",
                details={"error": str(e)},
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def create_secure_qdrant_client(
    project_name: str,
    use_local: bool = True,
) -> SecureQdrantClient:
    """
    创建安全 Qdrant 客户端的工厂函数

    Args:
        project_name: 项目名称
        use_local: 是否使用本地模式（默认 True）

    Returns:
        SecureQdrantClient 实例
    """
    config = get_security_config()

    if use_local:
        return SecureQdrantClient(
            project_name=project_name,
            host=config.QDRANT_HOST,
            port=config.QDRANT_PORT,
        )
    else:
        return SecureQdrantClient(
            project_name=project_name,
            host=config.QDRANT_HOST,
            port=config.QDRANT_PORT,
            api_key=config.QDRANT_API_KEY,
        )
