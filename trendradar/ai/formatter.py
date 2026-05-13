# coding=utf-8
"""
AI 分析结果格式化模块 - 选题提报增强版
适用版本：TrendRadar 6.6.x + 定制化选题报告
"""

import html as html_lib
import re
from .analyzer import AIAnalysisResult


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符，防止 XSS 攻击"""
    return html_lib.escape(text) if text else ""


def _format_list_content(text: str) -> str:
    """
    格式化提报内容，确保排版美观。
    处理数字序号换行、中文冒号对齐等逻辑。
    """
    if not text:
        return ""
    
    text = text.strip()

    # 1. 规范化：确保序号如 "一、" 或 "1." 后面有换行或空格，增强层级感
    # 针对中文序号进行换行增强
    text = re.sub(r'([一二三四五]、)', r'\n\1', text)
    
    # 2. 规范化：数字序号处理
    result = re.sub(r'(\d+)\.([^ \d])', r'\1. \2', text)

    # 3. 强制换行：匹配序号且前面不是换行符时，增加换行
    result = re.sub(r'(?<=[^\n])\s+([一二三四五]、|\d+\.)', r'\n\1', result)
    
    # 4. 优化中文标点后的间距
    result = re.sub(r'([：:;])\s*', r'\1\n', result)

    return result.strip()


def render_ai_analysis_markdown(result: AIAnalysisResult) -> str:
    """渲染为 Markdown 格式（用于企业微信、Telegram、ntfy、Slack）"""
    if not result.success:
        if result.skipped:
            return f"ℹ️ {result.error}"
        return f"⚠️ AI 分析失败: {result.error}"

    # 核心：提取定制化的提报内容
    content = getattr(result, "byd_report", "")
    
    # 兜底：如果 byd_report 为空但旧字段有值（兼容性处理）
    if not content and result.core_trends:
        content = result.core_trends

    if not content:
        return ""

    lines = [
        "**🚀 比亚迪专题选题提报**",
        "---",
        content,
        "",
        "*(由 DeepSeek AI 深度分析生成)*"
    ]
    return "\n".join(lines)


def render_ai_analysis_html_rich(result: AIAnalysisResult) -> str:
    """
    渲染为 HTML 报告样式。
    这是你在 output/html 文件夹里看到的那个精美报告的核心。
    """
    if not result or not result.success:
        error_msg = getattr(result, "error", "未知错误")
        return f'<div class="ai-error">⚠️ AI 分析无法显示: {error_msg}</div>'

    content = getattr(result, "byd_report", "")
    
    # 兼容性兜底
    if not content and hasattr(result, "core_trends"):
        content = result.core_trends

    if not content:
        return ""

    # 将换行符转为 HTML 的 <br> 以便正确显示
    formatted_content = _escape_html(content).replace("\n", "<br>")

    # 重新构建 HTML 结构，使用单栏长文模式，更适合阅读提报内容
    return f"""
    <div class="ai-section" style="background: #ffffff; border: 1px solid #e1e4e8; border-radius: 8px; overflow: hidden; margin-bottom: 20px;">
        <div class="ai-section-header" style="background: #f6f8fa; padding: 12px 16px; border-bottom: 1px solid #e1e4e8; display: flex; justify-content: space-between; align-items: center;">
            <div class="ai-section-title" style="font-weight: bold; color: #24292e; font-size: 16px;">✨ AI 比亚迪专题选题提报</div>
            <span class="ai-section-badge" style="background: #1890ff; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px;">DeepSeek</span>
        </div>
        <div class="ai-content-body" style="padding: 20px; line-height: 1.8; color: #333; font-size: 14px;">
            <div class="ai-report-text">
                {formatted_content}
            </div>
        </div>
        <div class="ai-footer" style="background: #fffbe6; padding: 8px 16px; font-size: 12px; color: #856404; border-top: 1px solid #ffe58f;">
            提示：点击“参考链接”可跳转至对应新闻详情进行核实。
        </div>
    </div>
    """


def render_ai_analysis_feishu(result: AIAnalysisResult) -> str:
    """渲染为飞书卡片格式"""
    return render_ai_analysis_markdown(result)


def render_ai_analysis_dingtalk(result: AIAnalysisResult) -> str:
    """渲染为钉钉格式"""
    if not result.success:
        return f"### ⚠️ AI 分析失败\n{result.error}"
    content = getattr(result, "byd_report", "")
    return f"### 🚀 比亚迪专题选题提报\n\n{content}"


def render_ai_analysis_plain(result: AIAnalysisResult) -> str:
    """渲染为纯文本格式"""
    content = getattr(result, "byd_report", "")
    return f"【✨ AI 选题提报】\n\n{content}"


def render_ai_analysis_telegram(result: AIAnalysisResult) -> str:
    """渲染为 Telegram HTML 格式"""
    if not result.success:
        return f"<b>⚠️ AI 分析失败</b>"
    content = getattr(result, "byd_report", "")
    return f"<b>🚀 比亚迪专题选题提报</b>\n\n{_escape_html(content)}"


def get_ai_analysis_renderer(channel: str):
    """
    根据推送渠道获取对应的渲染函数。
    """
    renderers = {
        "feishu": render_ai_analysis_feishu,
        "dingtalk": render_ai_analysis_dingtalk,
        "wework": render_ai_analysis_markdown, # 企业微信
        "telegram": render_ai_analysis_telegram,
        "email": render_ai_analysis_html_rich,  # 邮件使用丰富样式
        "ntfy": render_ai_analysis_markdown,
        "bark": render_ai_analysis_plain,
        "slack": render_ai_analysis_markdown,
    }
    # 默认返回 markdown 渲染器
    return renderers.get(channel, render_ai_analysis_markdown)


# 兼容性映射：确保老的调用代码 render_ai_analysis_html 不会失效
def render_ai_analysis_html(result: AIAnalysisResult) -> str:
    return render_ai_analysis_html_rich(result)
