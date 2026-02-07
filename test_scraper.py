"""
scraper.py 單元測試
==================
使用 mock 避免真實網路請求，測試所有核心邏輯。
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

import scraper


# ============================================================
# 平台識別
# ============================================================

class TestIdentifyPlatform:
    def test_ptt(self):
        r = scraper.identify_platform("https://www.ptt.cc/bbs/dog/M.123.html")
        assert r["name"] == "PTT"
        assert r["strategy"] == "jina"
        assert r["needs_login"] is False

    def test_medium(self):
        r = scraper.identify_platform("https://medium.com/@author/article")
        assert r["name"] == "Medium"

    def test_facebook_skip(self):
        r = scraper.identify_platform("https://www.facebook.com/post/123")
        assert r["name"] == "Facebook"
        assert r["strategy"] == "skip"
        assert r["needs_login"] is True

    def test_instagram_skip(self):
        r = scraper.identify_platform("https://www.instagram.com/p/abc")
        assert r["strategy"] == "skip"

    def test_vet_association_bs4_first(self):
        r = scraper.identify_platform("https://www.vetmed.org.tw/article/123")
        assert r["name"] == "獸醫學會"
        assert r["strategy"] == "bs4"

    def test_news_sites(self):
        for domain in ["udn.com", "ltn.com.tw", "ettoday.net", "cna.com.tw"]:
            r = scraper.identify_platform(f"https://www.{domain}/news/123")
            assert r["name"] == "新聞網站", f"Failed for {domain}"

    def test_unknown_defaults_to_jina(self):
        r = scraper.identify_platform("https://randomsite.example.org/page")
        assert r["name"] == "其他"
        assert r["strategy"] == "jina"

    def test_pixnet(self):
        r = scraper.identify_platform("https://vet.pixnet.net/blog/post/123")
        assert r["name"] == "痞客邦"

    def test_vocus(self):
        r = scraper.identify_platform("https://vocus.cc/article/abc")
        assert r["name"] == "方格子"

    def test_line_today(self):
        r = scraper.identify_platform("https://today.line.me/tw/v2/article/abc")
        assert r["name"] == "LINE TODAY"

    def test_wechat_playwright(self):
        r = scraper.identify_platform("https://mp.weixin.qq.com/s/abc")
        assert r["strategy"] == "playwright"

    def test_xiaohongshu_playwright(self):
        r = scraper.identify_platform("https://www.xiaohongshu.com/explore/abc")
        assert r["strategy"] == "playwright"


# ============================================================
# robots.txt 檢查
# ============================================================

class TestRobotsTxt:
    def test_allowed_when_no_robots(self):
        """無法取得 robots.txt 時應 fail-open"""
        with patch("scraper._get_robots_parser", return_value=None):
            assert scraper.is_allowed_by_robots("https://example.com/page") is True

    def test_allowed_when_parser_allows(self):
        mock_parser = MagicMock()
        mock_parser.can_fetch.return_value = True
        with patch("scraper._get_robots_parser", return_value=mock_parser):
            assert scraper.is_allowed_by_robots("https://example.com/page") is True

    def test_disallowed_when_parser_disallows(self):
        mock_parser = MagicMock()
        mock_parser.can_fetch.return_value = False
        with patch("scraper._get_robots_parser", return_value=mock_parser):
            assert scraper.is_allowed_by_robots("https://example.com/admin") is False

    def test_fail_open_on_exception(self):
        """解析過程出錯也應 fail-open"""
        with patch("scraper._get_robots_parser", side_effect=Exception("parse error")):
            assert scraper.is_allowed_by_robots("https://example.com/page") is True


# ============================================================
# 重試機制
# ============================================================

class TestRetryFetch:
    def test_success_first_try(self):
        func = MagicMock(return_value={"title": "ok"})
        result = scraper.retry_fetch(func, "https://example.com", max_retries=3)
        assert result == {"title": "ok"}
        assert func.call_count == 1

    def test_success_after_retries(self):
        func = MagicMock(side_effect=[None, None, {"title": "ok"}])
        with patch("time.sleep"):
            result = scraper.retry_fetch(func, "https://example.com", max_retries=3)
        assert result == {"title": "ok"}
        assert func.call_count == 3

    def test_all_retries_fail(self):
        func = MagicMock(return_value=None)
        with patch("time.sleep"):
            result = scraper.retry_fetch(func, "https://example.com", max_retries=3)
        assert result is None
        assert func.call_count == 3

    def test_exponential_backoff_delays(self):
        func = MagicMock(return_value=None)
        with patch("time.sleep") as mock_sleep:
            scraper.retry_fetch(func, "https://example.com", max_retries=3)
        # 預期延遲: 2*2^0=2, 2*2^1=4 (第三次失敗後不再 sleep)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(4)


# ============================================================
# 去重機制
# ============================================================

class TestDedup:
    def test_new_url_not_fetched(self, tmp_path):
        assert scraper.is_already_fetched("https://new.com/page", str(tmp_path)) is False

    def test_mark_and_check(self, tmp_path):
        url = "https://example.com/article"
        scraper.mark_as_fetched(url, str(tmp_path))
        assert scraper.is_already_fetched(url, str(tmp_path)) is True

    def test_different_url_not_fetched(self, tmp_path):
        scraper.mark_as_fetched("https://a.com/1", str(tmp_path))
        assert scraper.is_already_fetched("https://b.com/2", str(tmp_path)) is False

    def test_multiple_urls(self, tmp_path):
        urls = ["https://a.com/1", "https://b.com/2", "https://c.com/3"]
        for u in urls:
            scraper.mark_as_fetched(u, str(tmp_path))
        for u in urls:
            assert scraper.is_already_fetched(u, str(tmp_path)) is True

    def test_dedup_file_persists(self, tmp_path):
        scraper.mark_as_fetched("https://test.com", str(tmp_path))
        dedup_file = tmp_path / scraper.DEDUP_FILE
        assert dedup_file.exists()
        data = json.loads(dedup_file.read_text(encoding="utf-8"))
        assert "https://test.com" in data

    def test_corrupted_dedup_file(self, tmp_path):
        """損壞的 dedup 檔案不應 crash"""
        dedup_file = tmp_path / scraper.DEDUP_FILE
        dedup_file.write_text("NOT JSON", encoding="utf-8")
        assert scraper.is_already_fetched("https://test.com", str(tmp_path)) is False


# ============================================================
# YAML 安全轉義
# ============================================================

class TestYamlSafe:
    def test_normal_title(self):
        assert scraper._yaml_safe_title("Hello World") == "Hello World"

    def test_quotes_escaped(self):
        assert scraper._yaml_safe_title('Title "with" quotes') == 'Title \\"with\\" quotes'

    def test_backslash_escaped(self):
        assert scraper._yaml_safe_title("Path\\to\\file") == "Path\\\\to\\\\file"

    def test_combined(self):
        result = scraper._yaml_safe_title('Say "hello" \\ world')
        assert result == 'Say \\"hello\\" \\\\ world'

    def test_empty(self):
        assert scraper._yaml_safe_title("") == ""


# ============================================================
# Jina Reader
# ============================================================

class TestFetchWithJina:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.text = "Title: Test Article\n\n# Test\n\nSome content here that is long enough to pass validation. " * 5
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            result = scraper.fetch_with_jina("https://example.com/article")
        assert result is not None
        assert result["title"] == "Test Article"
        assert result["source"] == "jina"

    def test_content_too_short(self):
        mock_resp = MagicMock()
        mock_resp.text = "short"
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp):
            result = scraper.fetch_with_jina("https://example.com/article")
        assert result is None

    def test_network_error(self):
        import requests as req
        with patch("requests.get", side_effect=req.exceptions.ConnectionError("timeout")):
            result = scraper.fetch_with_jina("https://example.com/article")
        assert result is None

    def test_api_key_header(self):
        mock_resp = MagicMock()
        mock_resp.text = "Title: Test\n\n" + "content " * 50
        mock_resp.raise_for_status = MagicMock()

        with patch("requests.get", return_value=mock_resp) as mock_get, \
             patch.object(scraper, "JINA_API_KEY", "test-key-123"):
            scraper.fetch_with_jina("https://example.com")
            call_headers = mock_get.call_args[1].get("headers") or mock_get.call_args[0][1] if len(mock_get.call_args[0]) > 1 else mock_get.call_args[1]["headers"]
            assert call_headers.get("Authorization") == "Bearer test-key-123"


# ============================================================
# Jina 標題提取
# ============================================================

class TestExtractTitleFromJina:
    def test_title_prefix(self):
        assert scraper._extract_title_from_jina("Title: My Article\ncontent") == "My Article"

    def test_h1_heading(self):
        assert scraper._extract_title_from_jina("# My Heading\ncontent") == "My Heading"

    def test_no_title(self):
        assert scraper._extract_title_from_jina("just some content\nno title") == "未命名文章"

    def test_title_preferred_over_h1(self):
        content = "Title: From Title\n# From H1\ncontent"
        assert scraper._extract_title_from_jina(content) == "From Title"


# ============================================================
# BeautifulSoup 策略
# ============================================================

class TestFetchWithBs4:
    def _make_response(self, html, encoding="utf-8"):
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.apparent_encoding = encoding
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def test_success_with_article_tag(self):
        html = "<html><head><title>Test</title></head><body><article><p>This is a long enough article content for testing purposes and validation.</p></article></body></html>"
        with patch("requests.get", return_value=self._make_response(html)):
            result = scraper.fetch_with_bs4("https://example.com/page")
        assert result is not None
        assert result["source"] == "bs4"

    def test_content_too_short(self):
        html = "<html><body><article><p>Hi</p></article></body></html>"
        with patch("requests.get", return_value=self._make_response(html)):
            result = scraper.fetch_with_bs4("https://example.com/page")
        assert result is None

    def test_encoding_none_fallback(self):
        html = "<html><head><title>Test</title></head><body><article><p>Content that is definitely long enough for testing.</p></article></body></html>"
        with patch("requests.get", return_value=self._make_response(html, encoding=None)):
            result = scraper.fetch_with_bs4("https://example.com/page")
        assert result is not None

    def test_network_error(self):
        import requests as req
        with patch("requests.get", side_effect=req.exceptions.ConnectionError("connection refused")):
            result = scraper.fetch_with_bs4("https://example.com/page")
        assert result is None

    def test_extracts_h1_title(self):
        html = "<html><head><title>Page Title</title></head><body><h1>H1 Title</h1><article><p>This article content is definitely long enough to pass the fifty character minimum validation threshold for the BeautifulSoup extraction strategy.</p></article></body></html>"
        with patch("requests.get", return_value=self._make_response(html)):
            result = scraper.fetch_with_bs4("https://example.com/page")
        assert result is not None
        assert result["title"] == "H1 Title"


# ============================================================
# fetch_article 整合
# ============================================================

class TestFetchArticle:
    def test_skip_platform(self):
        result = scraper.fetch_article("https://www.facebook.com/post/123")
        assert result is None

    def test_robots_blocked(self):
        with patch("scraper.is_allowed_by_robots", return_value=False):
            result = scraper.fetch_article("https://example.com/page")
        assert result is None

    def test_jina_success(self):
        mock_result = {"title": "Test", "content": "x" * 200, "source": "jina", "url": "https://example.com"}
        with patch("scraper.is_allowed_by_robots", return_value=True), \
             patch("scraper.retry_fetch", return_value=mock_result):
            result = scraper.fetch_article("https://example.com/page")
        assert result is not None
        assert result["platform"] == "其他"

    def test_fallback_to_bs4(self):
        mock_result = {"title": "Test", "content": "x" * 200, "source": "bs4", "url": "https://example.com"}
        with patch("scraper.is_allowed_by_robots", return_value=True), \
             patch("scraper.retry_fetch", side_effect=[None, mock_result]):
            result = scraper.fetch_article("https://example.com/page")
        assert result is not None

    def test_all_strategies_fail(self):
        with patch("scraper.is_allowed_by_robots", return_value=True), \
             patch("scraper.retry_fetch", return_value=None):
            result = scraper.fetch_article("https://example.com/page")
        assert result is None


# ============================================================
# 圖片下載
# ============================================================

class TestDownloadImage:
    def test_success(self, tmp_path):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [b"fake image data"]
        mock_resp.raise_for_status = MagicMock()

        save_path = tmp_path / "img.jpg"
        with patch("requests.get", return_value=mock_resp):
            assert scraper.download_image("https://example.com/img.jpg", save_path) is True
        assert save_path.exists()
        assert save_path.read_bytes() == b"fake image data"

    def test_failure(self, tmp_path):
        save_path = tmp_path / "img.jpg"
        with patch("requests.get", side_effect=Exception("404")):
            assert scraper.download_image("https://example.com/img.jpg", save_path) is False
        assert not save_path.exists()


# ============================================================
# save_article
# ============================================================

class TestSaveArticle:
    def _make_article(self, title="Test Title", url="https://example.com/article"):
        return {
            "title": title,
            "content": "Some markdown content",
            "source": "jina",
            "url": url,
            "platform": "其他",
        }

    def test_creates_directory_structure(self, tmp_path):
        article = self._make_article()
        result = scraper.save_article(article, str(tmp_path))
        assert result.exists()
        assert (result / "content.md").exists()
        assert (result / "metadata.json").exists()
        assert (result / "images").is_dir()

    def test_yaml_frontmatter_format(self, tmp_path):
        article = self._make_article(title='Title with "quotes"')
        result = scraper.save_article(article, str(tmp_path))
        content = (result / "content.md").read_text(encoding="utf-8")
        assert "---" in content
        assert 'title: "Title with \\"quotes\\""' in content

    def test_metadata_json(self, tmp_path):
        article = self._make_article()
        result = scraper.save_article(article, str(tmp_path))
        meta = json.loads((result / "metadata.json").read_text(encoding="utf-8"))
        assert meta["title"] == "Test Title"
        assert meta["url"] == "https://example.com/article"
        assert meta["platform"] == "其他"

    def test_title_collision_gets_hash(self, tmp_path):
        a1 = self._make_article(url="https://a.com/1")
        a2 = self._make_article(url="https://b.com/2")
        p1 = scraper.save_article(a1, str(tmp_path))
        p2 = scraper.save_article(a2, str(tmp_path))
        assert p1 != p2
        assert p1.exists()
        assert p2.exists()


# ============================================================
# _guess_extension
# ============================================================

class TestGuessExtension:
    def test_jpg(self):
        assert scraper._guess_extension("https://img.com/photo.jpg") == ".jpg"

    def test_png(self):
        assert scraper._guess_extension("https://img.com/photo.png") == ".png"

    def test_webp(self):
        assert scraper._guess_extension("https://img.com/photo.webp") == ".webp"

    def test_with_query_string(self):
        assert scraper._guess_extension("https://img.com/photo.jpg?w=800") == ".jpg"

    def test_unknown_defaults_jpg(self):
        assert scraper._guess_extension("https://img.com/photo") == ".jpg"


# ============================================================
# batch_fetch
# ============================================================

class TestBatchFetch:
    def test_batch_with_dedup(self, tmp_path):
        url_file = tmp_path / "urls.txt"
        url_file.write_text("https://example.com/1\nhttps://example.com/2\n", encoding="utf-8")

        mock_article = {"title": "T", "content": "C", "source": "jina", "url": "https://example.com/1", "platform": "其他"}
        with patch("scraper.fetch_article", return_value=mock_article), \
             patch("scraper.save_article", return_value=tmp_path / "out"), \
             patch("time.sleep"):
            results = scraper.batch_fetch(str(url_file), str(tmp_path))
        assert len(results["success"]) == 2

    def test_batch_skips_already_fetched(self, tmp_path):
        url_file = tmp_path / "urls.txt"
        url_file.write_text("https://example.com/1\n", encoding="utf-8")
        scraper.mark_as_fetched("https://example.com/1", str(tmp_path))

        results = scraper.batch_fetch(str(url_file), str(tmp_path))
        assert len(results["skipped"]) == 1
        assert results["skipped"][0]["reason"] == "已下載過"

    def test_batch_skips_facebook(self, tmp_path):
        url_file = tmp_path / "urls.txt"
        url_file.write_text("https://www.facebook.com/post/1\n", encoding="utf-8")

        results = scraper.batch_fetch(str(url_file), str(tmp_path))
        assert len(results["skipped"]) == 1

    def test_batch_comments_ignored(self, tmp_path):
        url_file = tmp_path / "urls.txt"
        url_file.write_text("# comment\nhttps://example.com/1\n", encoding="utf-8")

        mock_article = {"title": "T", "content": "C", "source": "jina", "url": "https://example.com/1", "platform": "其他"}
        with patch("scraper.fetch_article", return_value=mock_article), \
             patch("scraper.save_article", return_value=tmp_path / "out"), \
             patch("time.sleep"):
            results = scraper.batch_fetch(str(url_file), str(tmp_path))
        assert len(results["success"]) == 1
