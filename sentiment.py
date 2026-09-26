"""本地情感词典分析器：识别买家消息的正负情绪，零依赖、离线、无延迟。

用于：
1. 负情绪触发人工接管（配合 config 的 auto_manual_on_negative 开关）
2. 负情绪自动进入 badcase 日志复盘通道
3. 情绪注入回复生成，让机器人调整语气
"""


# 情绪词 → 权重（正值=正面，负值=负面；绝对值越大情绪越强）
_WORDS = {
    # 强负面
    "生气": -2.0, "失望": -2.0, "无语": -2.0, "坑": -2.0, "坑人": -2.0,
    "骗": -2.0, "假货": -2.0, "垃圾": -2.0, "差评": -2.0, "投诉": -2.0,
    "退款": -2.0, "退货": -2.0, "不要了": -2.0, "离谱": -2.0, "恼火": -2.0,
    "烂": -2.0, "破": -2.0, "骗子": -2.0, "虚假": -2.0, "翻车": -2.0,
    "太黑": -2.0, "太差": -2.0,
    # 轻负面
    "贵": -1.0, "慢": -1.0, "担心": -1.0, "犹豫": -1.0, "怀疑": -1.0,
    "质疑": -1.0, "亏": -1.0, "黑": -1.0, "催": -1.0, "着急": -1.0,
    "不满意": -1.5, "不好": -1.0, "不靠谱": -1.5, "划不来": -1.0, "不值": -1.0,
    # 轻正面
    "好": 1.0, "可以": 1.0, "不错": 1.0, "喜欢": 1.0, "满意": 1.0,
    "快": 1.0, "划算": 1.0, "靠谱": 1.0, "开心": 1.0, "感谢": 1.0,
    "谢谢": 1.0, "期待": 1.0, "信赖": 1.0, "好评": 1.0, "赞": 1.0,
    "实惠": 1.0, "便宜": 1.0, "优惠": 1.0, "放心": 1.0, "信得过": 1.0,
    # 强正面
    "棒": 2.0, "完美": 2.0, "给力": 2.0, "超赞": 2.0, "太棒": 2.0,
    "非常满意": 2.0, "太好了": 2.0, "顶": 2.0,
}

# 否定词：出现在情绪词之前时，取反
_NEGATIONS = ("不要", "没有", "不", "没", "别", "无", "非", "莫", "未", "毫无")

# 程度副词：出现在情绪词之前时，加权
_DEGREE = {
    "非常": 1.7, "特别": 1.7, "极其": 1.8, "超级": 1.8, "超": 1.7,
    "太": 1.6, "很": 1.5, "真": 1.4, "挺": 1.3, "蛮": 1.3,
    "有点": 0.8, "有些": 0.8, "稍微": 0.7, "略微": 0.7,
}

_NEGATIVE_THRESHOLD = -1.5
_POSITIVE_THRESHOLD = 1.5


class SentimentAnalyzer:
    """本地情感分析器。analyze(text) 返回 {score, label}。"""

    def __init__(self):
        # 按长度降序排列，优先匹配更长的词（如 "太贵" 优先于 "贵"）
        self._words = sorted(_WORDS.items(), key=lambda kv: len(kv[0]), reverse=True)
        self._negations = sorted(_NEGATIONS, key=len, reverse=True)
        self._degree = sorted(_DEGREE.items(), key=lambda kv: len(kv[0]), reverse=True)

    def analyze(self, text):
        """对文本做情感分析。

        Returns:
            dict: {"score": float, "label": "positive"|"neutral"|"negative"}
        """
        if not text:
            return {"score": 0.0, "label": "neutral"}

        score = 0.0
        hits = 0
        n = len(text)
        i = 0
        while i < n:
            matched = None
            for word, weight in self._words:
                if text.startswith(word, i):
                    matched = (word, weight)
                    break
            if matched:
                word, weight = matched
                ctx = text[max(0, i - 4):i]  # 情绪词前最多 4 字符的语境
                # 否定词取反
                for neg in self._negations:
                    if ctx.endswith(neg):
                        weight = -weight
                        break
                # 程度副词加权
                deg = 1.0
                for adv, factor in self._degree:
                    if ctx.endswith(adv):
                        deg = factor
                        break
                score += weight * deg
                hits += 1
                i += len(word)
            else:
                i += 1

        if not hits:
            return {"score": 0.0, "label": "neutral"}

        if score <= _NEGATIVE_THRESHOLD:
            label = "negative"
        elif score >= _POSITIVE_THRESHOLD:
            label = "positive"
        else:
            label = "neutral"

        return {"score": round(score, 2), "label": label}
