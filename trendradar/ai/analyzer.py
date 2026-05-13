# coding=utf-8
"""
AI 分析器模块

调用 AI 大模型对热点新闻进行深度分析
基于 LiteLLM 统一接口，支持 100+ AI 提供商
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from trendradar.ai.client import AIClient
from trendradar.ai.prompt_loader import load_prompt_template


@dataclass
class AIAnalysisResult:
    """AI 分析结果 - 仅保留比亚迪专题"""
    # 只保留这一个核心内容字段
    byd_report: str = ""        
    
    # 元数据保留用于程序运行
    raw_response: str = ""
    success: bool = False
    error: str = ""
    skipped: bool = False

    # 新闻数量统计
    total_news: int = 0                  # 总新闻数（热榜+RSS）
    analyzed_news: int = 0               # 实际分析的新闻数
    max_news_limit: int = 0              # 分析上限配置值
    hotlist_count: int = 0               # 热榜新闻数
    rss_count: int = 0                   # RSS 新闻数
    ai_mode: str = ""                    # AI 分析使用的模式


class AIAnalyzer:
    """AI 分析器"""

    def __init__(
        self,
        ai_config: Dict[str, Any],
        analysis_config: Dict[str, Any],
        get_time_func: Callable,
        debug: bool = False,
    ):
        self.ai_config = ai_config
        self.analysis_config = analysis_config
        self.get_time_func = get_time_func
        self.debug = debug
        self.client = AIClient(ai_config)

        valid, error = self.client.validate_config()
        if not valid:
            print(f"[AI] 配置警告: {error}")

        self.max_news = analysis_config.get("MAX_NEWS_FOR_ANALYSIS", 50)
        self.include_rss = analysis_config.get("INCLUDE_RSS", True)
        self.include_rank_timeline = analysis_config.get("INCLUDE_RANK_TIMELINE", False)
        self.include_standalone = analysis_config.get("INCLUDE_STANDALONE", False)
        self.language = analysis_config.get("LANGUAGE", "Chinese")

        self.system_prompt, self.user_prompt_template = load_prompt_template(
            analysis_config.get("PROMPT_FILE", "ai_analysis_prompt.txt"),
            label="AI",
        )

    def analyze(
        self,
        stats: List[Dict],
        rss_stats: Optional[List[Dict]] = None,
        report_mode: str = "daily",
        report_type: str = "当日汇总",
        platforms: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        standalone_data: Optional[Dict] = None,
    ) -> AIAnalysisResult:
        """执行 AI 分析"""
        
        model = self.ai_config.get("MODEL", "unknown")
        api_key = self.client.api_key or ""
        masked_key = f"{api_key[:5]}******" if len(api_key) >= 5 else "******"
        
        print(f"[AI] 模型: {model.replace('/', '/\u200b')}")
        print(f"[AI] Key : {masked_key}")

        if not self.client.api_key:
            return AIAnalysisResult(success=False, error="未配置 AI API Key")

        # 准备新闻内容并获取统计数据
        news_content, rss_content, hotlist_total, rss_total, analyzed_count = self._prepare_news_content(stats, rss_stats)
        total_news = hotlist_total + rss_total

        if not news_content and not rss_content:
            return AIAnalysisResult(
                success=False, skipped=True, error="无新增热点，跳过分析",
                total_news=total_news, hotlist_count=hotlist_total, rss_count=rss_total
            )

        # 构建提示词
        current_time = self.get_time_func().strftime("%Y-%m-%d %H:%M:%S")
        user_prompt = self.user_prompt_template
        user_prompt = user_prompt.replace("{report_mode}", report_mode)
        user_prompt = user_prompt.replace("{report_type}", report_type)
        user_prompt = user_prompt.replace("{current_time}", current_time)
        user_prompt = user_prompt.replace("{news_count}", str(hotlist_total))
        user_prompt = user_prompt.replace("{rss_count}", str(rss_total))
        user_prompt = user_prompt.replace("{platforms}", ", ".join(platforms) if platforms else "多平台")
        user_prompt = user_prompt.replace("{keywords}", ", ".join(keywords[:20]) if keywords else "无")
        user_prompt = user_prompt.replace("{news_content}", news_content)
        user_prompt = user_prompt.replace("{rss_content}", rss_content)
        user_prompt = user_prompt.replace("{language}", self.language)

        standalone_content = self._prepare_standalone_content(standalone_data) if self.include_standalone and standalone_data else ""
        user_prompt = user_prompt.replace("{standalone_content}", standalone_content)

        if self.debug:
            print("\n[AI 调试] 提示词已构建完毕...")

        # 调用 AI
        try:
            response = self._call_ai(user_prompt)
            result = self._parse_response(response)

            # JSON 修复尝试
            if not result.success and "解析" in (result.error or ""):
                print(f"[AI] 尝试修复 JSON...")
                retry_result = self._retry_fix_json(response, result.error)
                if retry_result and retry_result.success:
                    result = retry_result

            # 填充统计数据
            result.total_news = total_news
            result.hotlist_count = hotlist_total
            result.rss_count = rss_total
            result.analyzed_news = analyzed_count
            result.max_news_limit = self.max_news
            return result
        except Exception as e:
            return AIAnalysisResult(success=False, error=f"AI 异常: {str(e)[:200]}")

    def _prepare_news_content(self, stats: List[Dict], rss_stats: Optional[List[Dict]]) -> tuple:
        news_lines, rss_lines = [], []
        news_count, rss_count = 0, 0
        hotlist_total = sum(len(s.get("titles", [])) for s in stats) if stats else 0
        rss_total = sum(len(s.get("titles", [])) for s in rss_stats) if rss_stats else 0

        if stats:
            for stat in stats:
                word = stat.get("word", "")
                titles = stat.get("titles", [])
                if word and titles:
                    news_lines.append(f"\n**{word}**")
                    for t in titles:
                        source = t.get("source_name", t.get("source", ""))
                        line = f"- [{source}] {t.get('title', '')}"
                        news_lines.append(line)
                        news_count += 1
                        if news_count >= self.max_news: break
                if news_count >= self.max_news: break

        return "\n".join(news_lines), "\n".join(rss_lines), hotlist_total, rss_total, (news_count + rss_count)

    def _call_ai(self, user_prompt: str) -> str:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        return self.client.chat(messages)

    def _retry_fix_json(self, original_response: str, error_msg: str) -> Optional[AIAnalysisResult]:
        messages = [
            {"role": "system", "content": "你是一个 JSON 修复助手。只返回纯 JSON。"},
            {"role": "user", "content": f"修复以下 JSON：\n{original_response}\n错误：{error_msg}"}
        ]
        try:
            response = self.client.chat(messages)
            return self._parse_response(response)
        except:
            return None

    def _format_time_range(self, first_time: str, last_time: str) -> str:
        return f"{first_time[:5]}~{last_time[:5]}" if first_time and last_time else "-"

    def _format_rank_timeline(self, rank_timeline: List[Dict]) -> str:
        return "→".join([f"{item.get('rank')}({item.get('time')})" for item in rank_timeline]) if rank_timeline else "-"

    def _prepare_standalone_content(self, standalone_data: Dict) -> str:
        lines = []
        for platform in standalone_data.get("platforms", []):
            lines.append(f"### {platform.get('name', '')}")
            for item in platform.get("items", []):
                lines.append(f"- {item.get('title', '')}")
        return "\n".join(lines)

    def _parse_response(self, response: str) -> AIAnalysisResult:
        """解析 AI 响应 - 核心解析函数 (唯一版)"""
        result = AIAnalysisResult(raw_response=response)
        if not response or not response.strip():
            result.error = "AI 返回空响应"
            return result

        # 提取 JSON
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("
```")[1].split("```")[0]

        json_str = json_str.strip()
        
        # 解析
        data = None
        try:
            data = json.loads(json_str)
        except:
            try:
                from json_repair import repair_json
                data = repair_json(json_str, return_objects=True)
            except:
                pass

        if isinstance(data, dict) and "byd_report" in data:
            result.byd_report = data.get("byd_report", "")
            result.success = True
        else:
            result.byd_report = json_str
            result.success = True
            result.error = "JSON 结构不匹配，已存储原始文本"

        return result
