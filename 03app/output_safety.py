"""Shared, conservative display filter; original research files stay untouched.

This is a small deterministic output boundary, not a claim to identify every
possible form of personal data. Apply it to model output *and* quoted material.
"""
from __future__ import annotations

from copy import deepcopy
import html
import re
import unicodedata
from urllib.parse import unquote, urlsplit


HIDDEN = "[个人联系方式已隐藏]"
CONTACT_POLICY = (
    "Do not output, recommend, reproduce, or expose personal contact information "
    "contained in the provided materials. Do not recommend contacting specific "
    "private individuals. When suggesting services, only mention publicly "
    "verifiable organizations, products, official websites, or general teacher profiles."
)

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+\s*@\s*[\w-]+(?:\s*\.\s*[\w-]+)+", re.I)
_OBFUSCATED_EMAIL = re.compile(
    r"[\w.+-]+\s*(?:\[at\]|\(at\)|\bat\b)\s*[\w-]+"
    r"\s*(?:\[dot\]|\(dot\)|\bdot\b|\.)\s*[A-Za-z]{2,}", re.I
)
_MOBILE = re.compile(r"(?<!\d)(?:(?:\+|00)?86[\s().-]*)?1[\s().-]*[3-9](?:[\s().-]*\d){9}(?!\d)")
_INTERNATIONAL_PHONE = re.compile(r"(?<!\w)\+\d(?:[\s().-]*\d){7,14}(?!\d)")
_CONTACT_LABEL = re.compile(
    r"(?:微信(?:号|号码|联系|咨询|二维码)?|微\s*信\s*号?|V\s*信|微\s*[xX]|薇信|威信|"
    r"(?<![A-Za-z])v\s*[xX](?![A-Za-z])|wechat|weixin|"
    r"QQ(?:号|号码|群)?|扣扣|企鹅号|手机(?:号|号码)?|电话|联系电话|联系号码|"
    r"邮箱|电子邮件|e[- ]?mail|phone|mobile|telephone|contact|私信(?:号|方式)?|联系方式|个人账号|个人帐号|"
    r"社媒账号|社交账号|私人账号|私人帐号|二维码|扫码(?:咨询|联系|添加|加|领取|进群)|"
    r"whats\s*app|telegram|signal\s*(?:id|number)|line\s*id)", re.I
)
_LABEL_VALUE = re.compile(
    r"(?:微信|V\s*信|V\s*X|wechat|weixin|QQ|扣扣|手机|电话|邮箱|私信|联系方式|"
    r"账号|帐号|phone|mobile|telephone|contact|whatsapp|telegram)[^\n:：=]{0,8}[:：=]\s*\S+", re.I
)
_CONTACT_CTA = re.compile(
    r"(?:加我|添加我|加好友|加为好友|加微|加V|加v|私聊|私信|扫码|扫一扫|"
    r"联系(?:我|本人|老师|教师|私教|顾问|博主)|咨询(?:本人|老师|顾问)|"
    r"(?:微信|VX|V信|QQ|邮箱|电话).{0,10}(?:咨询|联系|添加|同号|沟通|预约|搜索)|"
    r"(?:联系|添加|咨询|搜索|同号).{0,10}(?:微信|VX|V信|QQ|邮箱|手机)|"
    r"(?:DM|PM)\s+(?:me|us|@)|(?:contact|message|email|call)\s+me\b|"
    r"(?:add|reach)\s+me\b)", re.I
)
_CONTACT_VALUE = re.compile(
    r"(?:微信|V\s*信|微\s*[xX]|薇信|威信|(?<![a-z])V\s*X(?![a-z])|wechat|weixin|QQ|扣扣|"
    r"telegram|whatsapp)\s*(?:号|号码|ID|账号|帐号)?\s*[:：=\-（(\[]?\s*"
    r"[A-Za-z0-9_][A-Za-z0-9_+\-.\s]{2,}", re.I
)
_HANDLE = re.compile(r"(?<![\w/])@[A-Za-z0-9_][A-Za-z0-9_.-]{2,}")
_SOCIAL_ACCOUNT = re.compile(
    r"(?:小红书|抖音|微博|快手|B站|Instagram|TikTok|Twitter|Facebook|YouTube)"
    r"\s*(?:号|账号|帐号|ID|用户名)\s*[:：=]?\s*\S+", re.I
)
_NAMED_TEACHER = re.compile(
    r"(?:推荐|建议|联系|咨询|预约|找|添加|对接|选择).{0,14}"
    r"(?:[王李张刘陈赵黄周吴徐孙胡朱高林何郭马罗梁宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文][\u4e00-\u9fff]{0,2}|[A-Z][a-z]{1,18})"
    r"\s*(?:老师|教师|教练|导师)|"
    r"(?:contact|message|book|reach|recommend|try).{0,24}"
    r"(?:Mr\.?|Mrs\.?|Ms\.?|Miss|Teacher|Tutor)\s+[A-Z][A-Za-z]+|"
    r"(?:[王李张刘陈赵黄周吴徐孙胡朱高林何郭马罗梁宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文][\u4e00-\u9fff]{0,2}|[A-Z][a-z]{1,18})"
    r"\s*(?:老师|教师|教练|导师)[^。！？\n]{0,25}(?:适合你|值得推荐|可以联系|提供辅导|预约|报名|试听)", re.I
)
_URL = re.compile(r"(?:https?://|www\.)[^\s<>\[\]{}\"'，。！？；）]+|(?:mailto|tel|weixin|wechat|qq|whatsapp|tg):[^\s<>]+", re.I)
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)|!\[[^\]]*\]\[[^\]]*\]")
_HTML_IMAGE = re.compile(r"<(?:img|svg|canvas|iframe|object|embed|picture)\b[^>]*>(?:.*?</(?:svg|canvas|iframe|object|picture)\s*>)?", re.I | re.S)
_CONTACT_KEYS = {
    "phone", "phone_number", "mobile", "mobile_number", "telephone", "tel", "email", "e_mail",
    "private_email", "personal_email", "contact", "contacts", "contact_info", "contact_information",
    "contact_details", "contact_person", "wechat", "wechat_id", "weixin", "weixin_id", "vx", "qq",
    "qq_id", "qq_number", "whatsapp", "telegram", "social_handle", "social_account", "personal_account",
    "qrcode", "qr_code", "qr_url", "qr_code_url", "qr_content", "qr_code_content",
    "api_key", "apikey", "authorization", "access_token", "refresh_token", "password", "secret", "client_secret",
    "微信", "微信号", "手机号", "手机", "电话", "邮箱", "联系方式", "个人联系方式", "二维码", "联系老师",
}


def _normal(value):
    text = unicodedata.normalize("NFKC", html.unescape(str(value)))
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]", "", text)
    # Decode escaped contact values for detection only; never rewrite original sources.
    for _ in range(2):
        decoded = unquote(text)
        if decoded == text:
            break
        text = decoded
    return text


def _has_contact(value):
    text = _normal(value)
    return any(pattern.search(text) for pattern in (
        _EMAIL, _OBFUSCATED_EMAIL, _MOBILE, _INTERNATIONAL_PHONE, _LABEL_VALUE, _CONTACT_CTA,
        _CONTACT_VALUE, _HANDLE, _SOCIAL_ACCOUNT, _NAMED_TEACHER,
    )) or bool(re.search(r"二维码|扫码|QR\s*code", text, re.I))


def sanitize_url(url):
    """Keep public HTTP(S) resource URLs; hide contact endpoints and private profiles."""
    if not isinstance(url, str) or not url.strip():
        return ""
    original = url.strip()
    normalized = _normal(original)
    if _has_contact(normalized):
        return ""
    candidate = "https://" + normalized if normalized.lower().startswith("www.") else normalized
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return ""
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        return ""
    host = parts.hostname.lower().removeprefix("www.")
    path = parts.path.lower()
    if host in {"wa.me", "api.whatsapp.com", "t.me", "telegram.me", "qm.qq.com", "u.wechat.com", "weixin.qq.com"}:
        return ""
    if (host.endswith("xiaohongshu.com") and "/user/" in path
            or host.endswith("douyin.com") and "/user/" in path
            or host.endswith("zhihu.com") and re.search(r"/(?:people|org)/", path)
            or host.endswith("weibo.com") and re.search(r"/(?:u/)?[\w-]+/?$", path)
            or host in {"x.com", "twitter.com", "instagram.com", "facebook.com"}
            and len([part for part in path.split("/") if part]) <= 1
            or host.endswith("tiktok.com") and "/@" in path
            or host.endswith("bilibili.com") and host.startswith("space.")
            or host.endswith("youtube.com") and path.startswith("/@")):
        return ""
    # Contact-bearing query parameters and embedded local/path names are output too.
    if re.search(r"(?:^|[?&/])(?:wechat|weixin|wxid|qq|phone|mobile|email|contact|qrcode|qr_code)(?:=|/)", candidate, re.I):
        return ""
    return original


def _contact_field(key):
    normalized = _normal(key).strip().casefold().replace("-", "_").replace(" ", "_")
    return normalized in _CONTACT_KEYS or bool(re.fullmatch(
        r"(?:personal|private|teacher|tutor|advisor|consultant)_(?:contact|phone|email|wechat|qq|handle|account)(?:_.*)?", normalized
    ))


def _current_brand(text):
    text = text.replace("English Education Opportunity Explorer", "English Education Explorer")
    text = text.replace("英语教育需求与机会探索器", "英探探：英语学习与教育探索器")
    # Directory and launch-file references remain executable and traceable.
    return re.sub(r"(?<![A-Za-z0-9_/\\.])EngEduScope(?![A-Za-z0-9_/\\]|\.[A-Za-z0-9])",
                  "English Education Explorer", text, flags=re.I)


def sanitize_text(text):
    """Remove contact-bearing sentences, unsafe links, and uninspected images.

    Sentence removal avoids turning a recommendation to contact a private person
    into a misleading fragment. Safe neighbouring sentences remain readable.
    """
    if text is None:
        return ""
    original = _current_brand(str(text))
    if not original:
        return original
    cleaned = _MARKDOWN_IMAGE.sub("", original)
    cleaned = _HTML_IMAGE.sub("", cleaned)
    # PDF/OCR can wrap a single phone number or e-mail onto another line.
    for pattern in (_MOBILE, _INTERNATIONAL_PHONE, _EMAIL):
        cleaned = pattern.sub(lambda match: HIDDEN if "\n" in match[0] else match[0], cleaned)
    # A split label/value (e.g. OCR's '微信：\\nabc_123') must not leave the ID behind.
    lines = cleaned.splitlines(keepends=True)
    kept = []
    hide_next_value = False
    for line in lines:
        normalized = _normal(line).strip().strip(" >*_`#|-").strip()
        if hide_next_value:
            if normalized:
                hide_next_value = False
            continue
        if (_CONTACT_LABEL.search(normalized) and re.search(r"[:：=]\s*$", normalized)
                or _CONTACT_LABEL.fullmatch(normalized)):
            hide_next_value = True
            continue
        # Entity semicolons are markup, not sentence boundaries (teacher&#64;...).
        if html.unescape(line) != line and _has_contact(line):
            continue
        sentences = re.split(r"(?<=[。！？!?；;])(?=\s*[^\n])|(?<=\.)\s+(?=[A-Z\u4e00-\u9fff])", line)
        for sentence in sentences:
            if _has_contact(sentence):
                continue
            urls = _URL.findall(sentence)
            if any(not sanitize_url(url.rstrip(".,;:!)")) for url in urls):
                continue
            # Block unsafe HTML actions even when there is no matching plain URL.
            if re.search(r"(?:href|src)\s*=\s*[\"']?\s*(?:data|javascript|file):", _normal(sentence), re.I):
                continue
            kept.append(sentence)
    result = "".join(kept).strip()
    if not result and original.strip():
        return HIDDEN
    return result


def sanitize_data(value):
    """Return a filtered copy with the original JSON structure and safe IDs intact."""
    if isinstance(value, dict):
        # Some sources store a label and value separately, e.g. type=微信, value=ID.
        contact_record = any(
            str(key).casefold() in {"type", "kind", "label", "name", "field", "channel", "platform"}
            and isinstance(child, str) and _CONTACT_LABEL.fullmatch(_normal(child).strip())
            for key, child in value.items()
        )
        result = {}
        for key, child in value.items():
            if (_contact_field(key) or contact_record and str(key).casefold() in {
                    "value", "id", "account", "handle", "number", "url", "text", "content", "code", "data"}):
                result[key] = HIDDEN
                continue
            safe_key = sanitize_text(key) if isinstance(key, str) else key
            if safe_key == HIDDEN:
                continue
            if isinstance(child, str) and re.fullmatch(r"(?:url|source_url|original_url|website|homepage|link|official_url)", str(key), re.I):
                # Local paths are represented separately in source metadata.
                result[safe_key] = sanitize_url(child) if child else child
            else:
                result[safe_key] = sanitize_data(child)
        return result
    if isinstance(value, list):
        return [sanitize_data(child) for child in value]
    if isinstance(value, tuple):
        return tuple(sanitize_data(child) for child in value)
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and _MOBILE.search(str(value)):
        return HIDDEN
    return deepcopy(value)
