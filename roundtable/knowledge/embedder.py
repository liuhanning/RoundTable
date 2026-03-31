"""
P1-1: BGE-M3 本地 Embedding 模型

功能：
1. 本地文本向量化（无需 API）
2. 支持 BGE-M3 多语言模型
3. 批量编码优化
4. 与 SecureQdrantClient 集成

BGE-M3 特点：
- 支持 100+ 语言
- 向量维度：1024
- 支持稠密检索、稀疏检索、多向量检索
- 本地推理，无网络依赖
"""
import os
import threading
from dataclasses import dataclass
from typing import List, Optional, Union
from pathlib import Path

from utils.logger import get_sensitive_logger, get_audit_logger
from config import get_model_config


logger = get_sensitive_logger(__name__)
audit_logger = get_audit_logger()


# BGE-M3 模型配置
@dataclass
class BGEConfig:
    """BGE-M3 模型配置"""
    model_name: str = "BAAI/bge-m3"
    vector_size: int = 1024
    max_seq_length: int = 8192  # BGE-M3 支持长文本
    batch_size: int = 32
    device: Optional[str] = None  # 自动检测 CUDA/MPS/CPU


BGE_M3_CONFIG = BGEConfig()


class EmbeddingError(Exception):
    """Embedding 错误"""
    pass


class BGEModel:
    """
    BGE-M3 本地嵌入模型

    使用 SentenceTransformers 库加载 BGE-M3 模型
    支持：
    1. 单文本编码
    2. 批量编码
    3. 归一化向量（用于 Cosine 相似度）
    """

    def __init__(
        self,
        model_name: str = BGE_M3_CONFIG.model_name,
        device: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ):
        """
        初始化 BGE 模型

        Args:
            model_name: 模型名称（HuggingFace 格式）
            device: 设备 (None=自动，'cuda', 'mps', 'cpu')
            cache_dir: 模型缓存目录
        """
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir or "data/models"
        self.model = None
        self.tokenizer = None
        self._lock = threading.Lock()  # 线程安全的懒加载

        # 确保缓存目录存在
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

        logger.info(f"BGE 模型初始化：model={model_name}, cache={self.cache_dir}")
        audit_logger.log_event(
            event_type="model_init",
            resource="bge_embedder",
            action="init",
            result="success",
            details={"model_name": model_name, "cache_dir": self.cache_dir},
        )

    def _load_model(self):
        """懒加载模型（线程安全）"""
        if self.model is not None:
            return

        # 双重检查锁定模式，避免重复加载
        with self._lock:
            if self.model is not None:
                return

            try:
                # 尝试使用 FlagEmbedding (BGE 官方库)
                from FlagEmbedding import FlagModel
                self.model = FlagModel(
                    self.model_name,
                    query_instruction_for_retrieval=None,
                    use_fp16=True,  # 使用 FP16 节省显存
                )
                logger.info(f"使用 FlagEmbedding 加载 BGE 模型：{self.model_name}")

            except ImportError:
                # 降级到 SentenceTransformers
                try:
                    from sentence_transformers import SentenceTransformer
                    self.model = SentenceTransformer(
                        self.model_name,
                        device=self.device,
                        cache_folder=self.cache_dir,
                    )
                    logger.info(f"使用 SentenceTransformers 加载 BGE 模型：{self.model_name}")

                except ImportError:
                    raise EmbeddingError(
                        "未安装 Embedding 库，请运行：pip install FlagEmbedding 或 pip install sentence-transformers"
                    )

    def encode(
        self,
        text: Union[str, List[str]],
        normalize: bool = True,
        batch_size: int = BGE_M3_CONFIG.batch_size,
    ) -> Union[List[float], List[List[float]]]:
        """
        编码文本为向量

        Args:
            text: 单个文本或文本列表
            normalize: 是否归一化向量（用于 Cosine 相似度）
            batch_size: 批量大小

        Returns:
            单个向量或向量列表

        Raises:
            EmbeddingError: 当输入无效或编码失败时
        """
        self._load_model()

        # 输入验证
        if text is None:
            raise EmbeddingError("输入文本不能为 None")

        # 统一为列表处理
        is_single = isinstance(text, str)
        texts = [text] if is_single else text

        # 空列表处理
        if not texts:
            raise EmbeddingError("输入文本列表不能为空")

        # 验证空字符串
        if is_single and text.strip() == "":
            logger.warning("编码空字符串，可能返回无意义向量")

        try:
            # 使用 FlagEmbedding
            if hasattr(self.model, 'encode_queries'):
                # FlagEmbedding 的 encode_queries 不支持 normalize 参数
                # 需要手动归一化
                embeddings = self.model.encode_queries(texts)
                if normalize:
                    import numpy as np
                    if len(embeddings.shape) == 1:
                        norm = np.linalg.norm(embeddings)
                        if norm > 0:
                            embeddings = embeddings / norm
                    else:
                        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                        norms = np.where(norms == 0, 1, norms)  # 避免除零
                        embeddings = embeddings / norms
            else:
                # SentenceTransformers
                embeddings = self.model.encode(
                    texts,
                    batch_size=batch_size,
                    normalize_embeddings=False,  # 总是关闭内置归一化，统一手动处理
                    show_progress_bar=len(texts) > BGE_M3_CONFIG.batch_size,
                )
                # 手动归一化
                if normalize:
                    import numpy as np
                    if len(embeddings.shape) == 1:
                        norm = np.linalg.norm(embeddings)
                        if norm > 0:
                            embeddings = embeddings / norm
                    else:
                        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
                        norms = np.where(norms == 0, 1, norms)
                        embeddings = embeddings / norms

            # 转换为 Python 列表
            if len(embeddings.shape) == 1:
                result = embeddings.tolist()
            else:
                result = embeddings.tolist()

            return result[0] if is_single else result

        except Exception as e:
            logger.error(f"编码失败：{e}", exc_info=True)
            raise EmbeddingError(f"文本编码失败：{e}")

    def encode_documents(
        self,
        documents: List[str],
        batch_size: int = BGE_M3_CONFIG.batch_size,
    ) -> List[List[float]]:
        """
        编码文档列表（用于知识库向量化）

        Args:
            documents: 文档列表
            batch_size: 批量大小

        Returns:
            向量列表

        Raises:
            EmbeddingError: 当输入无效或编码失败时
        """
        if not documents:
            raise EmbeddingError("文档列表不能为空")
        return self.encode(documents, normalize=True, batch_size=batch_size)

    def get_vector_size(self) -> int:
        """获取向量维度"""
        return BGE_M3_CONFIG.vector_size

    def get_model_info(self) -> dict:
        """获取模型信息"""
        return {
            "model_name": self.model_name,
            "vector_size": self.get_vector_size(),
            "device": self.device or "auto",
            "cache_dir": self.cache_dir,
            "loaded": self.model is not None,
        }

    def close(self):
        """
        释放模型资源

        调用后模型实例不可用，需要重新初始化
        """
        if self.model is not None:
            # FlagEmbedding 和 SentenceTransformers 都没有正式的 close 方法
            # 这里显式删除引用以释放内存
            self.model = None
            logger.info("BGE 模型资源已释放")


# 全局模型实例（单例）
_embedder: Optional[BGEModel] = None
_embedder_lock = threading.Lock()


def get_embedder(
    model_name: str = BGE_M3_CONFIG.model_name,
    device: Optional[str] = None,
) -> BGEModel:
    """
    获取 BGE 嵌入模型（单例，线程安全）

    Args:
        model_name: 模型名称
        device: 设备

    Returns:
        BGEModel 实例
    """
    global _embedder
    if _embedder is None or _embedder.model_name != model_name:
        with _embedder_lock:
            # 双重检查
            if _embedder is None or _embedder.model_name != model_name:
                _embedder = BGEModel(model_name=model_name, device=device)
    return _embedder


def reset_embedder():
    """
    重置全局 embedder 实例（主要用于测试）

    调用后需要重新调用 get_embedder() 获取新实例
    """
    global _embedder
    if _embedder is not None:
        _embedder.close()
        _embedder = None


def encode_text(
    text: Union[str, List[str]],
    model_name: Optional[str] = None,
) -> Union[List[float], List[List[float]]]:
    """
    便捷函数：编码文本

    Args:
        text: 文本或文本列表
        model_name: 模型名称（可选）

    Returns:
        向量或向量列表

    Raises:
        EmbeddingError: 当输入无效或编码失败时
    """
    model_name = model_name or BGE_M3_CONFIG.model_name
    embedder = get_embedder(model_name)
    return embedder.encode(text)


def encode_documents(
    documents: List[str],
    model_name: Optional[str] = None,
) -> List[List[float]]:
    """
    便捷函数：编码文档列表

    Args:
        documents: 文档列表
        model_name: 模型名称（可选）

    Returns:
        向量列表

    Raises:
        EmbeddingError: 当输入无效或编码失败时
    """
    model_name = model_name or BGE_M3_CONFIG.model_name
    embedder = get_embedder(model_name)
    return embedder.encode_documents(documents)
