"""
BGE-M3 本地 Embedding 模型测试
测试覆盖：Happy Path + 边界条件 + 异常路径 + 集成场景
"""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

from knowledge.embedder import (
    BGEModel,
    EmbeddingError,
    get_embedder,
    encode_text,
    encode_documents,
    BGE_M3_CONFIG,
    reset_embedder,
)


# =============================================================================
# TestBGEModel - 核心模型测试
# =============================================================================
class TestBGEModel:
    """BGE 模型基础测试"""

    def test_model_init(self):
        """测试模型初始化"""
        model = BGEModel()
        assert model.model_name == "BAAI/bge-m3"
        assert model.cache_dir == "data/models"
        assert model.model is None  # 懒加载

    def test_model_init_custom_params(self):
        """测试自定义参数初始化"""
        model = BGEModel(
            model_name="BAAI/bge-large",
            device="cuda",
            cache_dir="/tmp/models",
        )
        assert model.model_name == "BAAI/bge-large"
        assert model.device == "cuda"
        assert model.cache_dir == "/tmp/models"

    def test_cache_dir_created(self, tmp_path):
        """测试缓存目录自动创建"""
        cache_dir = str(tmp_path / "new_models")
        model = BGEModel(cache_dir=cache_dir)
        assert Path(cache_dir).exists()

    def test_get_vector_size(self):
        """测试向量维度"""
        model = BGEModel()
        assert model.get_vector_size() == 1024

    def test_get_model_info_not_loaded(self):
        """测试获取模型信息（未加载）"""
        model = BGEModel()
        info = model.get_model_info()
        assert info["model_name"] == "BAAI/bge-m3"
        assert info["vector_size"] == 1024
        assert info["loaded"] is False

    def test_load_model_no_backend(self, monkeypatch):
        """测试无可用后端时错误"""
        model = BGEModel()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("FlagEmbedding", "sentence_transformers"):
                raise ImportError(name)
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        with pytest.raises(EmbeddingError) as exc_info:
            model._load_model()

        assert "未安装 Embedding 库" in str(exc_info.value)

    def test_encode_empty_list_raises(self, monkeypatch):
        """测试空列表抛出异常"""
        model = BGEModel()
        mock_instance = MagicMock()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        with pytest.raises(EmbeddingError) as exc_info:
            model.encode([])

        assert "不能为空" in str(exc_info.value)

    def test_encode_none_raises(self, monkeypatch):
        """测试 None 输入抛出异常"""
        model = BGEModel()
        mock_instance = MagicMock()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        with pytest.raises(EmbeddingError) as exc_info:
            model.encode(None)

        assert "不能为 None" in str(exc_info.value)

    def test_encode_documents_raises(self, monkeypatch):
        """测试 encode_documents 对空列表抛出异常"""
        model = BGEModel()
        mock_instance = MagicMock()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        with pytest.raises(EmbeddingError) as exc_info:
            model.encode_documents([])

        assert "不能为空" in str(exc_info.value)

    def test_model_close(self, monkeypatch):
        """测试模型资源释放"""
        model = BGEModel()
        mock_instance = MagicMock()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        # 加载模型
        model._load_model()
        assert model.model is not None

        # 关闭模型
        model.close()
        assert model.model is None


# =============================================================================
# TestSingleton - 单例模式测试
# =============================================================================
class TestSingleton:
    """单例模式测试"""

    def test_get_embedder_singleton(self):
        """测试单例模式"""
        reset_embedder()

        model1 = get_embedder()
        model2 = get_embedder()

        assert model1 is model2

    def test_get_embedder_different_model(self):
        """测试不同模型名称时重新创建"""
        reset_embedder()

        model1 = get_embedder(model_name="BAAI/bge-m3")
        model2 = get_embedder(model_name="BAAI/bge-large")

        assert model1 is not model2

    def test_reset_embedder(self):
        """测试重置 embedder"""
        reset_embedder()
        reset_embedder()

        model = get_embedder()
        assert model is not None

    def test_encode_text_function(self):
        """测试便捷函数 encode_text"""
        reset_embedder()

        with patch.object(BGEModel, 'encode', return_value=[0.1, 0.2]) as mock_encode:
            result = encode_text("测试")
            assert result == [0.1, 0.2]
            mock_encode.assert_called_once()

    def test_encode_documents_function(self):
        """测试便捷函数 encode_documents"""
        reset_embedder()

        with patch.object(BGEModel, 'encode_documents', return_value=[[0.1, 0.2]]) as mock_encode:
            result = encode_documents(["文档"])
            assert result == [[0.1, 0.2]]
            mock_encode.assert_called_once()


# =============================================================================
# TestIntegration - 集成场景测试
# =============================================================================
class TestIntegration:
    """集成场景测试"""

    def test_vector_normalization_flagembedding(self, monkeypatch):
        """测试 FlagEmbedding 向量归一化"""
        import numpy as np
        model = BGEModel()
        mock_instance = MagicMock()
        # FlagEmbedding 返回 numpy 数组
        raw_vector = np.array([3.0, 4.0])
        mock_instance.encode_queries.return_value = np.array([raw_vector])

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        result = model.encode(["测试"], normalize=True)

        # 验证归一化（模长应接近 1）
        norm = np.linalg.norm(result[0])
        assert abs(norm - 1.0) < 0.001

    def test_batch_encoding_consistency(self, monkeypatch):
        """测试批量编码一致性"""
        import numpy as np
        model = BGEModel()
        mock_instance = MagicMock()
        mock_instance.encode_queries.return_value = np.array([
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
            [0.7, 0.8, 0.9],
        ])

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        batch_result = model.encode(["文本 1", "文本 2", "文本 3"])

        assert len(batch_result) == 3
        assert all(len(v) == 3 for v in batch_result)

    def test_model_info_after_load(self, monkeypatch):
        """测试加载后的模型信息"""
        model = BGEModel()
        mock_instance = MagicMock()

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        model._load_model()

        info = model.get_model_info()
        assert info["loaded"] is True
        assert info["model_name"] == "BAAI/bge-m3"
        assert info["vector_size"] == 1024


# =============================================================================
# TestEdgeCases - 边界条件测试
# =============================================================================
class TestEdgeCases:
    """边界条件测试"""

    def test_empty_string_warning(self, monkeypatch, caplog):
        """测试空字符串编码告警"""
        import logging
        import numpy as np
        model = BGEModel()
        mock_instance = MagicMock()
        mock_instance.encode_queries.return_value = np.array([[0.0] * 1024])

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        with caplog.at_level(logging.WARNING):
            result = model.encode("")

        assert "空字符串" in caplog.text
        assert isinstance(result, list)

    def test_very_long_text(self, monkeypatch):
        """测试超长文本编码"""
        import numpy as np
        model = BGEModel()
        mock_instance = MagicMock()
        mock_instance.encode_queries.return_value = np.array([[0.1] * 1024])

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        long_text = "测试 " * 1000
        result = model.encode(long_text)

        assert len(result) == 1024

    def test_unicode_text_encoding(self, monkeypatch):
        """测试 Unicode 文本编码"""
        import numpy as np
        model = BGEModel()
        mock_instance = MagicMock()
        mock_instance.encode_queries.return_value = np.array([[0.1] * 1024])

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        texts = ["中文测试", "English test", "テスト", "🔥🚀💻"]

        for text in texts:
            result = model.encode(text)
            assert len(result) == 1024

    def test_manual_normalization(self, monkeypatch):
        """测试 FlagEmbedding 后端的手动归一化"""
        import numpy as np
        model = BGEModel()
        mock_instance = MagicMock()
        raw_vector = np.array([3.0, 4.0, 0.0])
        mock_instance.encode_queries.return_value = np.array([raw_vector])

        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "FlagEmbedding":
                module = MagicMock()
                module.FlagModel = MagicMock(return_value=mock_instance)
                return module
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        result = model.encode(["测试"], normalize=True)

        norm = np.linalg.norm(result[0])
        assert abs(norm - 1.0) < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
