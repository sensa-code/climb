"""
ai_processor.py 單元測試
========================
使用 mock 避免真實 API 呼叫，測試所有核心邏輯。
"""

import json
import os
import threading
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import ai_processor


# ============================================================
# Frontmatter 解析
# ============================================================

class TestParseFrontmatter:
    def test_basic_parse(self):
        """解析標準 YAML frontmatter"""
        content = """---
title: "Test Article"
platform: PTT
tags: []
---

Article body here."""
        fm, body = ai_processor.parse_frontmatter(content)
        assert fm["title"] == "Test Article"
        assert fm["platform"] == "PTT"
        assert fm["tags"] == []
        assert "Article body here." in body

    def test_no_frontmatter(self):
        """沒有 frontmatter 的內容"""
        content = "Just a plain text article."
        fm, body = ai_processor.parse_frontmatter(content)
        assert fm == {}
        assert body == content

    def test_empty_content(self):
        """空字串"""
        fm, body = ai_processor.parse_frontmatter("")
        assert fm == {}
        assert body == ""

    def test_tags_as_list(self):
        """標籤以列表格式解析"""
        content = '---\ntags: ["CKD", "cat", "renal"]\n---\nBody'
        fm, body = ai_processor.parse_frontmatter(content)
        assert fm["tags"] == ["CKD", "cat", "renal"]

    def test_quoted_values(self):
        """帶引號的值"""
        content = "---\ntitle: \"Hello: World\"\nsource: 'https://example.com'\n---\nBody"
        fm, body = ai_processor.parse_frontmatter(content)
        assert fm["title"] == "Hello: World"
        assert fm["source"] == "https://example.com"

    def test_empty_string_value(self):
        """空字串值"""
        content = '---\ncategory: ""\nsummary: \'\'\n---\nBody'
        fm, body = ai_processor.parse_frontmatter(content)
        assert fm["category"] == ""
        assert fm["summary"] == ""

    def test_multiline_value(self):
        """PyYAML 可以解析多行值"""
        content = '---\ntitle: Test\nsummary: |-\n  第一行\n  第二行\n---\nBody'
        fm, body = ai_processor.parse_frontmatter(content)
        assert fm["title"] == "Test"
        assert "第一行" in fm["summary"]
        assert "第二行" in fm["summary"]

    def test_special_chars_roundtrip(self):
        """特殊字元經過讀寫後保持一致"""
        original = '---\ntitle: "文章: 含冒號的標題"\nsource: "https://example.com/path?q=1&b=2"\n---\nBody'
        fm, body = ai_processor.parse_frontmatter(original)
        assert fm["title"] == "文章: 含冒號的標題"
        assert fm["source"] == "https://example.com/path?q=1&b=2"

        # roundtrip
        updated = ai_processor.update_frontmatter(original, {})
        fm2, _ = ai_processor.parse_frontmatter(updated)
        assert fm2["title"] == fm["title"]
        assert fm2["source"] == fm["source"]

    def test_nested_list_values(self):
        """PyYAML 正確處理列表值"""
        content = '---\ntags:\n  - CKD\n  - 貓\n  - 老年\n---\nBody'
        fm, body = ai_processor.parse_frontmatter(content)
        assert fm["tags"] == ["CKD", "貓", "老年"]


# ============================================================
# Frontmatter 更新
# ============================================================

class TestUpdateFrontmatter:
    def test_add_new_fields(self):
        """新增欄位到現有 frontmatter"""
        content = "---\ntitle: Test\nplatform: PTT\n---\nBody"
        updated = ai_processor.update_frontmatter(content, {
            "category": "內科/腎臟",
            "tags": ["CKD", "cat"],
        })
        fm, body = ai_processor.parse_frontmatter(updated)
        assert fm["title"] == "Test"
        assert fm["platform"] == "PTT"
        assert fm["category"] == "內科/腎臟"
        assert fm["tags"] == ["CKD", "cat"]
        assert "Body" in body

    def test_update_existing_fields(self):
        """更新已存在的欄位"""
        content = "---\ntitle: Test\ncategory: 其他\n---\nBody"
        updated = ai_processor.update_frontmatter(content, {
            "category": "內科/心臟",
        })
        fm, _ = ai_processor.parse_frontmatter(updated)
        assert fm["category"] == "內科/心臟"

    def test_preserve_other_fields(self):
        """更新時保留其他欄位"""
        content = "---\ntitle: Test\nplatform: Medium\ndate: 2024-01-01\n---\nBody"
        updated = ai_processor.update_frontmatter(content, {
            "summary": "A test summary",
        })
        fm, _ = ai_processor.parse_frontmatter(updated)
        assert fm["title"] == "Test"
        assert fm["platform"] == "Medium"
        # PyYAML 會將 2024-01-01 解析為 datetime.date 物件
        assert str(fm["date"]) == "2024-01-01"
        assert fm["summary"] == "A test summary"

    def test_no_existing_frontmatter(self):
        """對沒有 frontmatter 的內容新增"""
        content = "Just body text"
        updated = ai_processor.update_frontmatter(content, {
            "title": "New Title",
            "tags": [],
        })
        fm, body = ai_processor.parse_frontmatter(updated)
        assert fm["title"] == "New Title"
        assert fm["tags"] == []
        assert "Just body text" in body

    def test_empty_tags_list(self):
        """空標籤列表"""
        content = "---\ntitle: Test\n---\nBody"
        updated = ai_processor.update_frontmatter(content, {"tags": []})
        fm, _ = ai_processor.parse_frontmatter(updated)
        assert fm["tags"] == []


# ============================================================
# 文章掃描
# ============================================================

class TestScanArticles:
    def _create_article(self, base_dir, name, platform="PTT",
                        category="", summary=""):
        """建立測試用文章目錄"""
        article_dir = os.path.join(base_dir, name)
        os.makedirs(article_dir, exist_ok=True)

        fm_lines = [
            "---",
            f'title: "{name}"',
            f"platform: {platform}",
        ]
        if category:
            fm_lines.append(f"category: {category}")
        if summary:
            fm_lines.append(f"summary: {summary}")
        fm_lines.extend(["tags: []", "---", "", "Article content here."])

        with open(os.path.join(article_dir, "content.md"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(fm_lines))

        meta = {"title": name, "platform": platform}
        with open(os.path.join(article_dir, "metadata.json"), "w",
                  encoding="utf-8") as f:
            json.dump(meta, f)

        return article_dir

    def test_finds_articles(self, tmp_path):
        """找到文章目錄"""
        self._create_article(str(tmp_path), "2024-01-01_TestArticle")
        self._create_article(str(tmp_path), "2024-01-02_AnotherArticle")

        articles = ai_processor.scan_articles(str(tmp_path))
        assert len(articles) == 2

    def test_marks_processed(self, tmp_path):
        """已有 AI 資料的文章標記為已處理"""
        self._create_article(str(tmp_path), "processed",
                             category="內科/腎臟", summary="A summary")
        self._create_article(str(tmp_path), "unprocessed")

        articles = ai_processor.scan_articles(str(tmp_path))
        processed = [a for a in articles if a["has_ai_data"]]
        unprocessed = [a for a in articles if not a["has_ai_data"]]
        assert len(processed) == 1
        assert len(unprocessed) == 1

    def test_empty_directory(self, tmp_path):
        """空目錄回傳空列表"""
        articles = ai_processor.scan_articles(str(tmp_path))
        assert articles == []

    def test_nonexistent_directory(self):
        """不存在的目錄回傳空列表"""
        articles = ai_processor.scan_articles("/nonexistent/path")
        assert articles == []

    def test_skips_non_directories(self, tmp_path):
        """跳過非目錄的檔案"""
        (tmp_path / "random_file.txt").write_text("hello")
        articles = ai_processor.scan_articles(str(tmp_path))
        assert articles == []

    def test_article_char_count(self, tmp_path):
        """文章字元數計算"""
        self._create_article(str(tmp_path), "test")
        articles = ai_processor.scan_articles(str(tmp_path))
        assert articles[0]["char_count"] > 0


# ============================================================
# 費用估算
# ============================================================

class TestEstimateCost:
    def test_basic_estimate(self):
        """基本費用估算"""
        articles = [
            {"char_count": 2000, "has_ai_data": False},
            {"char_count": 3000, "has_ai_data": False},
        ]
        cost = ai_processor.estimate_cost(articles)
        assert cost["article_count"] == 2
        assert cost["total_chars"] > 0
        assert cost["estimated_cost_usd"] > 0
        assert cost["model"] == ai_processor.DEFAULT_MODEL

    def test_empty_list(self):
        """空列表回傳零費用"""
        cost = ai_processor.estimate_cost([])
        assert cost["article_count"] == 0
        assert cost["estimated_cost_usd"] == 0

    def test_skips_processed(self):
        """跳過已處理的文章"""
        articles = [
            {"char_count": 2000, "has_ai_data": True},
            {"char_count": 3000, "has_ai_data": False},
        ]
        cost = ai_processor.estimate_cost(articles)
        assert cost["article_count"] == 1

    def test_different_models(self):
        """不同模型有不同費用"""
        articles = [{"char_count": 5000, "has_ai_data": False}]
        sonnet_cost = ai_processor.estimate_cost(articles, "claude-sonnet-4-20250514")
        haiku_cost = ai_processor.estimate_cost(articles, "claude-haiku")
        assert haiku_cost["estimated_cost_usd"] < sonnet_cost["estimated_cost_usd"]

    def test_truncates_long_articles(self):
        """超長文章的字元數應被截斷"""
        articles = [{"char_count": 100000, "has_ai_data": False}]
        cost = ai_processor.estimate_cost(articles)
        assert cost["total_chars"] == ai_processor.MAX_ARTICLE_CHARS


# ============================================================
# 單篇文章處理
# ============================================================

class TestProcessSingleArticle:
    def test_no_anthropic(self):
        """未安裝 anthropic 時拋出 ImportError"""
        with patch.object(ai_processor, "HAS_ANTHROPIC", False):
            with pytest.raises(ImportError, match="anthropic"):
                ai_processor.process_single_article("text", "fake-key")

    def test_success_with_mock(self):
        """mock API 成功回傳分類結果"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({
                "category": "內科",
                "subcategory": "腎臟",
                "tags": ["CKD", "貓", "老年"],
                "summary": "這是一篇關於貓腎臟病的文章",
                "key_points": ["SDMA 是早期指標", "飲食管理很重要"],
                "clinical_relevance": "早期篩檢可改善預後",
            })
        )]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                mock_anthropic.Anthropic.return_value = mock_client
                result = ai_processor.process_single_article(
                    "Test article about cat CKD", "fake-key",
                )

        assert result["category"] == "內科"
        assert result["subcategory"] == "腎臟"
        assert "CKD" in result["tags"]
        assert len(result["summary"]) > 0

    def test_api_error(self):
        """不可重試的 API 錯誤拋出 RuntimeError"""
        import anthropic as real_anthropic

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.headers = {}
        bad_request = real_anthropic.BadRequestError(
            message="Bad request",
            response=mock_resp,
            body={"error": {"message": "Bad request"}},
        )
        mock_client.messages.create.side_effect = bad_request

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                mock_anthropic.APIConnectionError = real_anthropic.APIConnectionError
                mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
                mock_anthropic.RateLimitError = real_anthropic.RateLimitError
                mock_anthropic.InternalServerError = real_anthropic.InternalServerError
                mock_anthropic.AuthenticationError = real_anthropic.AuthenticationError
                mock_anthropic.BadRequestError = real_anthropic.BadRequestError
                mock_anthropic.APIStatusError = real_anthropic.APIStatusError
                mock_anthropic.APIError = real_anthropic.APIError
                mock_anthropic.Anthropic.return_value = mock_client
                with pytest.raises(RuntimeError, match="不可重試"):
                    ai_processor.process_single_article("text", "fake-key")

    def test_invalid_json_response(self):
        """非 JSON 回應拋出 RuntimeError"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="This is not JSON")]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                mock_anthropic.Anthropic.return_value = mock_client
                with pytest.raises(RuntimeError, match="JSON"):
                    ai_processor.process_single_article("text", "fake-key")

    def test_json_in_code_block(self):
        """從 markdown code block 中提取 JSON"""
        json_data = {
            "category": "外科",
            "subcategory": "眼科",
            "tags": ["角膜潰瘍", "犬"],
            "summary": "角膜潰瘍的處理",
            "key_points": ["緊急處理"],
            "clinical_relevance": "及時治療很重要",
        }
        response_text = f"Here is the result:\n```json\n{json.dumps(json_data)}\n```"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=response_text)]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                mock_anthropic.Anthropic.return_value = mock_client
                result = ai_processor.process_single_article("text", "fake-key")

        assert result["category"] == "外科"
        assert result["subcategory"] == "眼科"

    def test_missing_required_fields(self):
        """缺少必要欄位拋出 RuntimeError"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(
            text=json.dumps({"category": "內科"})  # missing tags, summary
        )]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                mock_anthropic.Anthropic.return_value = mock_client
                with pytest.raises(RuntimeError, match="缺少"):
                    ai_processor.process_single_article("text", "fake-key")

    def test_retry_on_connection_error(self):
        """連線錯誤自動重試，第 3 次成功"""
        import anthropic as real_anthropic

        good_response = MagicMock()
        good_response.content = [MagicMock(
            text=json.dumps({
                "category": "內科", "subcategory": "腎臟",
                "tags": ["CKD"], "summary": "Test summary",
                "key_points": ["P1"], "clinical_relevance": "重要",
            })
        )]

        mock_client = MagicMock()
        conn_error = real_anthropic.APIConnectionError(request=MagicMock())
        mock_client.messages.create.side_effect = [
            conn_error, conn_error, good_response,
        ]

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                # 讓 isinstance 檢查生效
                mock_anthropic.APIConnectionError = real_anthropic.APIConnectionError
                mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
                mock_anthropic.RateLimitError = real_anthropic.RateLimitError
                mock_anthropic.InternalServerError = real_anthropic.InternalServerError
                mock_anthropic.AuthenticationError = real_anthropic.AuthenticationError
                mock_anthropic.BadRequestError = real_anthropic.BadRequestError
                mock_anthropic.APIStatusError = real_anthropic.APIStatusError
                mock_anthropic.APIError = real_anthropic.APIError
                mock_anthropic.Anthropic.return_value = mock_client
                with patch("ai_processor.time.sleep"):  # 跳過延遲
                    result = ai_processor.process_single_article(
                        "text", "fake-key",
                    )

        assert result["category"] == "內科"
        assert mock_client.messages.create.call_count == 3

    def test_no_retry_on_auth_error(self):
        """401 認證錯誤不重試，直接失敗"""
        import anthropic as real_anthropic

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.headers = {}
        auth_error = real_anthropic.AuthenticationError(
            message="Invalid API Key",
            response=mock_resp,
            body={"error": {"message": "Invalid API Key"}},
        )
        mock_client.messages.create.side_effect = auth_error

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                mock_anthropic.APIConnectionError = real_anthropic.APIConnectionError
                mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
                mock_anthropic.RateLimitError = real_anthropic.RateLimitError
                mock_anthropic.InternalServerError = real_anthropic.InternalServerError
                mock_anthropic.AuthenticationError = real_anthropic.AuthenticationError
                mock_anthropic.BadRequestError = real_anthropic.BadRequestError
                mock_anthropic.APIStatusError = real_anthropic.APIStatusError
                mock_anthropic.APIError = real_anthropic.APIError
                mock_anthropic.Anthropic.return_value = mock_client
                with pytest.raises(RuntimeError, match="不可重試"):
                    ai_processor.process_single_article("text", "fake-key")

        # 只呼叫一次，沒有重試
        assert mock_client.messages.create.call_count == 1

    def test_retry_on_rate_limit(self):
        """429 rate limit 使用更長延遲重試"""
        import anthropic as real_anthropic

        good_response = MagicMock()
        good_response.content = [MagicMock(
            text=json.dumps({
                "category": "其他", "subcategory": "",
                "tags": ["test"], "summary": "OK",
                "key_points": [], "clinical_relevance": "",
            })
        )]

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        rate_error = real_anthropic.RateLimitError(
            message="Rate limit exceeded",
            response=mock_resp,
            body={"error": {"message": "Rate limit exceeded"}},
        )
        mock_client.messages.create.side_effect = [
            rate_error, good_response,
        ]

        sleep_calls = []

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                mock_anthropic.APIConnectionError = real_anthropic.APIConnectionError
                mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
                mock_anthropic.RateLimitError = real_anthropic.RateLimitError
                mock_anthropic.InternalServerError = real_anthropic.InternalServerError
                mock_anthropic.AuthenticationError = real_anthropic.AuthenticationError
                mock_anthropic.BadRequestError = real_anthropic.BadRequestError
                mock_anthropic.APIStatusError = real_anthropic.APIStatusError
                mock_anthropic.APIError = real_anthropic.APIError
                mock_anthropic.Anthropic.return_value = mock_client
                with patch("ai_processor.time.sleep", side_effect=lambda d: sleep_calls.append(d)):
                    result = ai_processor.process_single_article(
                        "text", "fake-key",
                    )

        assert result["category"] == "其他"
        # rate limit 使用 API_RATE_LIMIT_DELAY（30s）
        assert sleep_calls[0] == ai_processor.API_RATE_LIMIT_DELAY

    def test_max_retries_exceeded(self):
        """重試次數用盡後拋出 RuntimeError"""
        import anthropic as real_anthropic

        mock_client = MagicMock()
        conn_error = real_anthropic.APIConnectionError(request=MagicMock())
        mock_client.messages.create.side_effect = conn_error

        with patch.object(ai_processor, "HAS_ANTHROPIC", True):
            with patch("ai_processor.anthropic") as mock_anthropic:
                mock_anthropic.APIConnectionError = real_anthropic.APIConnectionError
                mock_anthropic.APITimeoutError = real_anthropic.APITimeoutError
                mock_anthropic.RateLimitError = real_anthropic.RateLimitError
                mock_anthropic.InternalServerError = real_anthropic.InternalServerError
                mock_anthropic.AuthenticationError = real_anthropic.AuthenticationError
                mock_anthropic.BadRequestError = real_anthropic.BadRequestError
                mock_anthropic.APIStatusError = real_anthropic.APIStatusError
                mock_anthropic.APIError = real_anthropic.APIError
                mock_anthropic.Anthropic.return_value = mock_client
                with patch("ai_processor.time.sleep"):
                    with pytest.raises(RuntimeError, match="重試.*次後仍然失敗"):
                        ai_processor.process_single_article("text", "fake-key")

        assert mock_client.messages.create.call_count == ai_processor.MAX_API_RETRIES


# ============================================================
# 批次處理
# ============================================================

class TestProcessArticleBatch:
    def _create_article_dir(self, base_dir, name, body="Test body content"):
        """建立測試用文章目錄"""
        article_dir = os.path.join(base_dir, name)
        os.makedirs(article_dir, exist_ok=True)

        content = f"---\ntitle: {name}\nplatform: Test\ntags: []\n---\n{body}"
        with open(os.path.join(article_dir, "content.md"), "w",
                  encoding="utf-8") as f:
            f.write(content)

        meta = {"title": name, "platform": "Test"}
        with open(os.path.join(article_dir, "metadata.json"), "w",
                  encoding="utf-8") as f:
            json.dump(meta, f)

        return {"path": article_dir, "title": name, "platform": "Test",
                "has_ai_data": False, "char_count": len(body)}

    def test_processes_all(self, tmp_path):
        """批次處理所有文章"""
        articles = [
            self._create_article_dir(str(tmp_path), "article1"),
            self._create_article_dir(str(tmp_path), "article2"),
        ]

        mock_result = {
            "category": "內科", "subcategory": "腎臟",
            "tags": ["CKD"], "summary": "Test summary",
            "key_points": ["Point 1"], "clinical_relevance": "Important",
        }

        with patch.object(ai_processor, "process_single_article",
                          return_value=mock_result):
            result = ai_processor.process_article_batch(
                articles, "fake-key", api_delay=0,
            )

        assert result["success"] == 2
        assert result["failed"] == 0

    def test_cancel_event(self, tmp_path):
        """取消事件中斷處理"""
        articles = [
            self._create_article_dir(str(tmp_path), f"article{i}")
            for i in range(5)
        ]

        cancel_event = threading.Event()
        cancel_event.set()  # 立即取消

        mock_result = {
            "category": "內科", "subcategory": "",
            "tags": [], "summary": "Test",
            "key_points": [], "clinical_relevance": "",
        }

        with patch.object(ai_processor, "process_single_article",
                          return_value=mock_result):
            result = ai_processor.process_article_batch(
                articles, "fake-key", api_delay=0,
                cancel_event=cancel_event,
            )

        # 立即取消，不應該處理任何文章
        assert result["success"] == 0

    def test_updates_frontmatter(self, tmp_path):
        """處理後 frontmatter 已更新"""
        articles = [
            self._create_article_dir(str(tmp_path), "test_article"),
        ]

        mock_result = {
            "category": "外科", "subcategory": "眼科",
            "tags": ["角膜", "犬"],
            "summary": "眼科手術相關",
            "key_points": ["術前評估"],
            "clinical_relevance": "重要",
        }

        with patch.object(ai_processor, "process_single_article",
                          return_value=mock_result):
            ai_processor.process_article_batch(
                articles, "fake-key", api_delay=0,
            )

        # 驗證 content.md 已更新
        content_path = os.path.join(articles[0]["path"], "content.md")
        with open(content_path, "r", encoding="utf-8") as f:
            content = f.read()
        fm, _ = ai_processor.parse_frontmatter(content)
        assert fm["category"] == "外科/眼科"
        assert "角膜" in fm["tags"]
        assert fm["summary"] == "眼科手術相關"

    def test_updates_metadata_json(self, tmp_path):
        """處理後 metadata.json 已更新"""
        articles = [
            self._create_article_dir(str(tmp_path), "test_article"),
        ]

        mock_result = {
            "category": "營養學", "subcategory": "",
            "tags": ["飲食", "腎病"],
            "summary": "營養管理",
            "key_points": ["控制蛋白質"],
            "clinical_relevance": "飲食很重要",
        }

        with patch.object(ai_processor, "process_single_article",
                          return_value=mock_result):
            ai_processor.process_article_batch(
                articles, "fake-key", api_delay=0,
            )

        # 驗證 metadata.json 已更新
        meta_path = os.path.join(articles[0]["path"], "metadata.json")
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["category"] == "營養學"
        assert "飲食" in meta["tags"]
        assert "ai_processed_at" in meta
        assert "ai_model" in meta

    def test_handles_api_failure(self, tmp_path):
        """API 失敗時記錄錯誤並繼續"""
        articles = [
            self._create_article_dir(str(tmp_path), "fail_article"),
            self._create_article_dir(str(tmp_path), "success_article"),
        ]

        call_count = 0

        def mock_process(text, key, model=None, max_tokens=None, title=""):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("API Error")
            return {
                "category": "其他", "subcategory": "",
                "tags": [], "summary": "OK",
                "key_points": [], "clinical_relevance": "",
            }

        with patch.object(ai_processor, "process_single_article",
                          side_effect=mock_process):
            result = ai_processor.process_article_batch(
                articles, "fake-key", api_delay=0,
            )

        assert result["success"] == 1
        assert result["failed"] == 1

    def test_progress_callback(self, tmp_path):
        """進度回調被正確呼叫"""
        articles = [
            self._create_article_dir(str(tmp_path), "article1"),
            self._create_article_dir(str(tmp_path), "article2"),
        ]

        progress_calls = []

        def on_progress(current, total, msg):
            progress_calls.append((current, total, msg))

        mock_result = {
            "category": "其他", "subcategory": "",
            "tags": [], "summary": "Test",
            "key_points": [], "clinical_relevance": "",
        }

        with patch.object(ai_processor, "process_single_article",
                          return_value=mock_result):
            ai_processor.process_article_batch(
                articles, "fake-key", api_delay=0,
                on_progress=on_progress,
            )

        # 應該有 2 次處理 + 1 次完成通知
        assert len(progress_calls) == 3
        assert progress_calls[-1][2] == "AI 處理完成"
