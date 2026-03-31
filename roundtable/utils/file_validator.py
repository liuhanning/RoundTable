"""
P0-2: 文件上传验证

安全红线：所有上传文件必须经过白名单验证、大小限制、魔法字节验证
防止恶意文件上传、服务器资源耗尽、XSS 攻击
"""
import os
import hashlib
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
from config import get_security_config


# 文件类型魔法字节签名（用于验证真实文件类型）
MAGIC_BYTES = {
    '.pdf': [b'%PDF-'],
    '.docx': [b'PK\x03\x04'],  # DOCX 本质是 ZIP
    '.xlsx': [b'PK\x03\x04'],
    '.pptx': [b'PK\x03\x04'],
    '.zip': [b'PK\x03\x04'],
    '.txt': None,  # 文本文件无特定魔法字节
    '.md': None,
}


class FileUploadValidationError(Exception):
    """文件上传验证异常"""
    pass


def validate_file_extension(filename: str) -> Tuple[bool, str]:
    """
    验证文件扩展名（白名单机制）

    Args:
        filename: 文件名

    Returns:
        (是否有效，错误信息)
    """
    security_config = get_security_config()

    ext = Path(filename).suffix.lower()

    if not ext:
        return False, "文件缺少扩展名"

    if ext not in security_config.ALLOWED_EXTENSIONS:
        allowed_str = ', '.join(security_config.ALLOWED_EXTENSIONS)
        return False, f"不支持的文件类型：{ext}（允许的类型：{allowed_str}）"

    return True, ""


def validate_file_size(file_size: int) -> Tuple[bool, str]:
    """
    验证文件大小

    Args:
        file_size: 文件大小（字节）

    Returns:
        (是否有效，错误信息)
    """
    security_config = get_security_config()

    if file_size <= 0:
        return False, "文件大小无效"

    if file_size > security_config.MAX_FILE_SIZE:
        max_mb = security_config.MAX_FILE_SIZE / 1024 / 1024
        actual_mb = file_size / 1024 / 1024
        return False, f"文件大小超出限制：{actual_mb:.2f}MB（最大允许：{max_mb}MB）"

    return True, ""


def validate_magic_bytes(content: bytes, extension: str) -> Tuple[bool, str]:
    """
    验证文件魔法字节（防止扩展名伪装）

    Args:
        content: 文件内容（字节）
        extension: 文件扩展名

    Returns:
        (是否有效，错误信息)
    """
    ext = extension.lower()

    # 文本类文件不需要魔法字节验证
    if MAGIC_BYTES.get(ext) is None:
        # 但至少检查是否包含合法的文本内容
        try:
            content.decode('utf-8')
            return True, ""
        except UnicodeDecodeError:
            try:
                content.decode('gbk')  # 支持中文编码
                return True, ""
            except:
                return False, "文件内容无法识别为文本格式"

    # 二进制文件验证魔法字节
    expected_signatures = MAGIC_BYTES[ext]

    if not expected_signatures:
        return True, ""  # 无签名要求

    for signature in expected_signatures:
        if content[:len(signature)] == signature:
            return True, ""

    return False, f"文件内容与扩展名不匹配（期望：{ext} 格式）"


def calculate_file_hash(content: bytes) -> str:
    """
    计算文件 SHA256 哈希（用于去重和完整性校验）

    Args:
        content: 文件内容

    Returns:
        SHA256 哈希字符串
    """
    return hashlib.sha256(content).hexdigest()


def validate_upload(
    filename: str,
    file_size: int,
    content: bytes
) -> Dict[str, Any]:
    """
    完整的文件上传验证流程

    防护层级：
    1. 扩展名白名单验证
    2. 文件大小限制
    3. 魔法字节验证（防止伪装）
    4. 内容扫描（可选，预留病毒扫描接口）

    Args:
        filename: 文件名
        file_size: 文件大小
        content: 文件内容

    Returns:
        验证结果：
        {
            "valid": bool,
            "error": str or None,
            "file_hash": str,  # 文件哈希
            "extension": str,  # 文件扩展名
            "mime_type": str,  # MIME 类型
        }
    """
    result = {
        "valid": False,
        "error": None,
        "file_hash": None,
        "extension": None,
        "mime_type": None,
    }

    # 1. 扩展名验证
    ext_valid, ext_error = validate_file_extension(filename)
    if not ext_valid:
        result["error"] = f"[扩展名验证失败] {ext_error}"
        return result

    ext = Path(filename).suffix.lower()
    result["extension"] = ext

    # 2. 文件大小验证
    size_valid, size_error = validate_file_size(file_size)
    if not size_valid:
        result["error"] = f"[大小验证失败] {size_error}"
        return result

    # 3. 魔法字节验证
    magic_valid, magic_error = validate_magic_bytes(content, ext)
    if not magic_valid:
        result["error"] = f"[内容验证失败] {magic_error}"
        return result

    # 4. 计算文件哈希
    result["file_hash"] = calculate_file_hash(content)

    # 5. 推断 MIME 类型
    result["mime_type"] = infer_mime_type(ext)

    # 全部通过
    result["valid"] = True

    return result


def infer_mime_type(extension: str) -> str:
    """
    根据扩展名推断 MIME 类型

    Args:
        extension: 文件扩展名

    Returns:
        MIME 类型字符串
    """
    mime_map = {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        '.txt': 'text/plain',
        '.md': 'text/markdown',
    }
    return mime_map.get(extension, 'application/octet-stream')


class FileUploadValidator:
    """
    文件上传验证器（有状态版本）

    提供额外功能：
    1. 文件去重（基于哈希）
    2. 上传统计
    3. 黑名单管理
    """

    def __init__(self):
        self.config = get_security_config()
        self.uploaded_hashes = set()  # 已上传文件哈希集合
        self.upload_count = 0
        self.rejected_count = 0

    def validate(self, filename: str, content: bytes) -> Dict[str, Any]:
        """验证并记录上传"""
        file_size = len(content)
        result = validate_upload(filename, file_size, content)

        self.upload_count += 1
        if not result["valid"]:
            self.rejected_count += 1

        # 检查重复文件
        if result["valid"] and result["file_hash"] in self.uploaded_hashes:
            result["valid"] = False
            result["error"] = "重复的文件（已基于哈希检测到重复）"
            result["is_duplicate"] = True
        else:
            result["is_duplicate"] = False

        # 记录已上传哈希
        if result["valid"] and result["file_hash"]:
            self.uploaded_hashes.add(result["file_hash"])

        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取上传统计"""
        return {
            "total_uploads": self.upload_count,
            "rejected": self.rejected_count,
            "unique_files": len(self.uploaded_hashes),
        }

    def clear_cache(self):
        """清空哈希缓存（释放内存）"""
        self.uploaded_hashes.clear()


# 全局验证器实例（单例）
_validator: Optional[FileUploadValidator] = None


def get_file_upload_validator() -> FileUploadValidator:
    """获取文件上传验证器（单例）"""
    global _validator
    if _validator is None:
        _validator = FileUploadValidator()
    return _validator
