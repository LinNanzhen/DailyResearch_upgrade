"""Email delivery for the daily digest.

Two providers, no extra services required:

- Resend  (recommended): RESEND_API_KEY. With the default sender
  `onboarding@resend.dev`, Resend only delivers to the account owner's own
  address — which is exactly the personal use case here.
- SMTP (Gmail / QQ / institutional): SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS.

Nothing is sent when no credentials are present; the digest itself still runs.
"""
from __future__ import annotations

import html as html_lib
import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

import requests

RESEND_ENDPOINT = "https://api.resend.com/emails"
DEFAULT_SITE = "https://linnanzhen.github.io/DailyResearch_upgrade/"

INK = "#12170f"
MUTED = "#5d675c"
FAINT = "#8b9387"
TEAL = "#0e5b52"
EOSIN = "#a63d40"
PAPER = "#eff1ea"
CARD = "#fafbf6"
BORDER = "#d9dcd2"
SERIF = "Georgia, 'Songti SC', 'Noto Serif SC', serif"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif"
MONO = "'SFMono-Regular', Consolas, 'Liberation Mono', monospace"


def _esc(value: Any) -> str:
    return html_lib.escape(str(value or ""))


def _cfg(profile: Dict[str, Any]) -> Dict[str, Any]:
    return ((profile.get("delivery") or {}).get("email") or {})


def _site(cfg: Dict[str, Any]) -> str:
    base = str(cfg.get("site_url") or DEFAULT_SITE).rstrip("/")
    return base


def day_url(day: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    return f"{_site(cfg)}/?date={day.get('date', '')}"


def subject_for(day: Dict[str, Any]) -> str:
    must = day.get("must_read") or {}
    title = must.get("title_zh") or must.get("title") or "今日四篇"
    title = str(title).strip()
    if len(title) > 46:
        title = title[:45] + "…"
    return f"{day.get('date', '')} · 口腔文献日课：{title}"


# ---------------------------------------------------------------- HTML parts
def _button(label: str, href: str, primary: bool = True) -> str:
    if primary:
        style = (
            f"display:inline-block;padding:10px 18px;background:{TEAL};color:#f7f8f3;"
            "text-decoration:none;font-size:13px;border-radius:2px;font-family:" + SANS
        )
    else:
        style = (
            f"display:inline-block;padding:10px 18px;background:transparent;color:{INK};"
            f"text-decoration:none;font-size:13px;border:1px solid {BORDER};border-radius:2px;font-family:{SANS}"
        )
    return f'<a href="{_esc(href)}" style="{style}">{_esc(label)}</a>'


def _section_label(text: str) -> str:
    return (
        f'<div style="font-family:{MONO};font-size:10px;letter-spacing:.14em;color:{FAINT};'
        f'text-transform:uppercase;padding:0 0 6px">{_esc(text)}</div>'
    )


def _must_read_block(day: Dict[str, Any], cfg: Dict[str, Any]) -> str:
    p = day.get("must_read")
    if not p:
        return ""
    deep = p.get("deep") or {}
    title = p.get("title_zh") or deep.get("title_zh") or p.get("title") or ""
    orig = p.get("title") if p.get("title_zh") else ""
    meta = " · ".join(str(x) for x in [
        p.get("journal"), p.get("date"), p.get("design_label"),
        p.get("sample_note"), f"{p.get('tier')} 级" if p.get("tier") else "",
    ] if x)
    score = (p.get("score") or {}).get("final")
    score_txt = f"{round(float(score))}" if score is not None else "—"

    rows: List[str] = []
    if deep:
        findings = deep.get("findings") or []
        findings_html = "".join(
            f'<div style="margin:0 0 10px"><div style="font-size:14.5px;font-weight:600;color:{INK}">{_esc(f.get("claim"))}</div>'
            f'<div style="font-family:{MONO};font-size:12px;color:{TEAL};line-height:1.6">{_esc(f.get("evidence"))}</div></div>'
            for f in findings
        )
        limits = "".join(f"<li style='margin:0 0 4px'>{_esc(x)}</li>" for x in (deep.get("limitations") or []))
        asks = "".join(
            f'<li style="margin:0 0 8px;font-size:14.5px">{_esc(q)}</li>' for q in (deep.get("followups") or [])
        )
        rows.append(f"""
        <tr><td style="padding:18px 0 0">
          {_section_label("主诉 / 问题")}
          <div style="font-size:15px;line-height:1.7;color:{INK}">{_esc(deep.get("question"))}</div>
        </td></tr>
        <tr><td style="padding:16px 0 0">
          {_section_label("检查 / 设计")}
          <div style="font-size:15px;line-height:1.7;color:{INK}">{_esc(deep.get("design"))}</div>
          <div style="font-size:13px;line-height:1.6;color:{MUTED};margin-top:4px">{_esc(deep.get("sample_desc"))}</div>
        </td></tr>
        <tr><td style="padding:16px 0 0">
          {_section_label("诊断 / 证据")}
          {findings_html}
          <div style="font-size:13px;color:{MUTED};margin-top:6px"><span style="font-family:{MONO};font-size:9.5px;letter-spacing:.1em;color:{EOSIN}">效应量&nbsp;</span>{_esc(deep.get("effect"))}</div>
        </td></tr>
        <tr><td style="padding:16px 0 0">
          {_section_label("处理 / 与我")}
          <div style="font-size:15px;line-height:1.7;color:{INK}">{_esc(deep.get("relation"))}</div>
          <div style="font-size:13.5px;line-height:1.7;color:{TEAL};margin-top:6px">可迁移：{_esc(deep.get("transferable"))}</div>
        </td></tr>""")
        if limits:
            rows.append(f"""
        <tr><td style="padding:18px 0 0">
          <div style="background:#f8eeee;border-left:2px solid {EOSIN};padding:12px 14px">
            <div style="font-family:{MONO};font-size:9.5px;letter-spacing:.12em;color:{EOSIN};margin-bottom:6px">读到这里要怀疑的地方</div>
            <ul style="margin:0;padding-left:16px;font-size:13px;line-height:1.7;color:{INK}">{limits}</ul>
          </div>
        </td></tr>""")
        if asks:
            rows.append(f"""
        <tr><td style="padding:20px 0 0">
          {_section_label("读完回答这三个问题")}
          <ol style="margin:0;padding-left:18px;color:{INK}">{asks}</ol>
        </td></tr>""")
    else:
        rows.append(f"""
        <tr><td style="padding:18px 0 0">
          <div style="font-family:{MONO};font-size:10.5px;line-height:1.7;color:{MUTED};border-left:2px solid {BORDER};padding:8px 12px">
            本次未接入模型，没有精读卡。下面是摘要。
          </div>
          <div style="font-size:14px;line-height:1.8;color:{MUTED};margin-top:12px">{_esc((p.get("abstract") or "")[:900])}…</div>
        </td></tr>""")

    return f"""
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:26px 0 0">
      <tr><td style="background:{CARD};border:1px solid {BORDER};padding:26px 28px 24px">
        <div style="font-family:{MONO};font-size:10px;letter-spacing:.16em;color:{TEAL};text-transform:uppercase">
          精读 · {_esc(p.get('tier') or 'C')} 级 · {_esc(p.get('cluster') or '')} · {score_txt} 分
        </div>
        <h1 style="margin:8px 0 6px;font-family:{SERIF};font-weight:500;font-size:26px;line-height:1.35;color:{INK}">{_esc(title)}</h1>
        {f'<div style="font-size:12.5px;line-height:1.5;color:{MUTED};margin:0 0 10px">{_esc(orig)}</div>' if orig else ''}
        <div style="font-family:{MONO};font-size:10.5px;color:{MUTED};padding-bottom:14px;border-bottom:1px dashed {BORDER}">{_esc(meta)}</div>
        {f'<div style="margin:16px 0 0;padding-left:14px;border-left:3px solid {TEAL};font-family:{SERIF};font-size:18px;line-height:1.55;color:{INK}">{_esc(p.get("one_line"))}</div>' if p.get("one_line") else ''}
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{''.join(rows)}</table>
        <div style="padding:22px 0 0">
          {_button("打开原文", p.get("url") or "#")}
          &nbsp;&nbsp;{_button("在网页里读", day_url(day, cfg), primary=False)}
        </div>
      </td></tr>
    </table>"""


def _scan_block(day: Dict[str, Any]) -> str:
    items = day.get("scan") or []
    if not items:
        return ""
    rows = []
    for i, p in enumerate(items):
        title = p.get("title_zh") or p.get("title") or ""
        score = (p.get("score") or {}).get("final")
        score_txt = f"{round(float(score))}" if score is not None else "—"
        rows.append(f"""
      <tr><td style="border-top:1px solid #e2e4da;padding:16px 0">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td valign="top" style="width:36px;font-family:{MONO};font-size:11px;color:{FAINT};padding-top:3px">{i + 2:02d}</td>
          <td valign="top">
            <a href="{_esc(p.get('url'))}" style="font-family:{SERIF};font-size:17px;line-height:1.4;color:{INK};text-decoration:none">{_esc(title)}</a>
            <div style="font-size:14px;line-height:1.65;color:{INK};margin-top:5px">{_esc(p.get('one_line'))}</div>
            {f'<div style="font-size:13px;line-height:1.6;color:{TEAL};margin-top:3px">→ {_esc(p.get("so_what"))}</div>' if p.get("so_what") else ''}
            {f'<div style="font-size:12.5px;line-height:1.6;color:{EOSIN};margin-top:4px">要打折扣：{_esc(p.get("caution"))}</div>' if p.get("caution") else ''}
            <div style="font-family:{MONO};font-size:10px;color:{FAINT};margin-top:6px">{_esc(" · ".join(str(x) for x in [p.get("journal"), p.get("design_label"), p.get("sample_note"), p.get("date")] if x))}</div>
          </td>
          <td valign="top" style="width:44px;text-align:right;font-family:{MONO};font-size:16px;color:{MUTED}">{score_txt}</td>
        </tr></table>
      </td></tr>""")
    return f"""
    <div style="font-family:{MONO};font-size:10px;letter-spacing:.16em;color:{EOSIN};text-transform:uppercase;margin:34px 0 2px">02 · 速览</div>
    <div style="font-size:12px;color:{MUTED};margin-bottom:4px">每篇 30 秒：做了什么 · 与我何关 · 哪里可能虚</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{''.join(rows)}</table>"""


def _weekly_block(day: Dict[str, Any]) -> str:
    w = day.get("weekly") or {}
    if not w:
        return ""
    clusters = "".join(
        f'<div style="padding:8px 0;border-top:1px solid #d5dac8">'
        f'<span style="font-family:{MONO};font-size:10px;letter-spacing:.06em;color:{TEAL}">{_esc(c.get("name"))} · {_esc(c.get("n"))} 篇</span>'
        f'<span style="font-size:13.5px;color:{INK}">　{_esc(c.get("insight"))}</span></div>'
        for c in (w.get("clusters") or [])
    )
    tension = w.get("tension") or {}
    tension_html = ""
    if tension:
        tension_html = (
            f'<div style="margin-top:12px;padding:12px 0;border-top:1px dashed {BORDER};border-bottom:1px dashed {BORDER};font-size:13.5px;line-height:1.7;color:{INK}">'
            f'{_esc(tension.get("a"))} <span style="font-family:{MONO};font-size:10px;color:{EOSIN};padding:0 8px">VS</span> {_esc(tension.get("b"))}'
            f'<div style="font-size:12.5px;color:{MUTED};margin-top:4px">{_esc(tension.get("note"))}</div></div>'
        )
    gaps = "".join(f"<li style='margin:0 0 4px'>{_esc(g)}</li>" for g in (w.get("gaps") or []))
    return f"""
    <div style="font-family:{MONO};font-size:10px;letter-spacing:.16em;color:{EOSIN};text-transform:uppercase;margin:34px 0 8px">03 · 本周地图</div>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="background:#e9ede1;border:1px solid {BORDER};padding:22px 24px">
        <div style="font-family:{SERIF};font-size:20px;line-height:1.45;color:{INK};margin-bottom:10px">{_esc(w.get("headline"))}</div>
        {clusters}
        {tension_html}
        {f'<div style="font-size:13px;color:{MUTED};margin-top:12px">方法迁移：{_esc(w.get("method_shift"))}</div>' if w.get("method_shift") else ''}
        {f'<div style="font-family:{MONO};font-size:10px;letter-spacing:.12em;color:{FAINT};margin-top:14px">可以做的空白</div><ul style="margin:6px 0 0;padding-left:16px;font-size:13.5px;line-height:1.7;color:{INK}">{gaps}</ul>' if gaps else ''}
      </td></tr>
    </table>"""


def render_email_html(day: Dict[str, Any], profile: Dict[str, Any]) -> str:
    cfg = _cfg(profile)
    stats = day.get("stats") or {}
    shown = (1 if day.get("must_read") else 0) + len(day.get("scan") or [])
    minutes = 20
    deep = (day.get("must_read") or {}).get("deep") or {}
    if deep.get("reading_minutes"):
        minutes = int(deep["reading_minutes"]) + 2 * len(day.get("scan") or [])
    funnel = (
        f'<span style="color:{INK};font-weight:600">{_esc(stats.get("candidates", "?"))}</span> 篇候选'
        f' → <span style="color:{INK};font-weight:600">{_esc(stats.get("gated", "?"))}</span> 篇过筛'
        f' → <span style="color:{TEAL};font-weight:600">{shown}</span> 篇留下 · 约 {minutes} 分钟'
    )
    banner = ""
    if not day.get("ai"):
        banner = (
            f'<div style="margin:18px 0 0;padding:10px 14px;border-left:2px solid #a9752a;background:#f6f0e2;'
            f'font-size:12.5px;line-height:1.7;color:#6a5325">本次未接入模型：只有确定性排序，没有精读卡与点评。</div>'
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(subject_for(day))}</title>
</head>
<body style="margin:0;padding:0;background:{PAPER};-webkit-font-smoothing:antialiased">
<div style="display:none;font-size:1px;color:{PAPER};max-height:0;overflow:hidden">今天只读四篇：1 篇精读，3 篇速览。</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{PAPER};padding:26px 12px">
  <tr><td align="center">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;max-width:100%">
      <tr><td>
        <div style="font-family:{MONO};font-size:10px;letter-spacing:.24em;color:{MUTED};text-transform:uppercase">口腔文献日课 · DAILY RESEARCH</div>
        <div style="font-family:{SERIF};font-size:40px;line-height:1;color:{INK};margin:8px 0 10px">{_esc(day.get("date"))}</div>
        <div style="font-family:{MONO};font-size:11px;color:{MUTED}">{funnel}</div>
        {banner}
      </td></tr>
      <tr><td>
        <div style="font-family:{MONO};font-size:10px;letter-spacing:.16em;color:{EOSIN};text-transform:uppercase;margin:28px 0 0">01 · 精读</div>
        {_must_read_block(day, cfg)}
      </td></tr>
      <tr><td>{_scan_block(day)}</td></tr>
      <tr><td>{_weekly_block(day)}</td></tr>
      <tr><td style="padding:30px 0 0">
        <div style="border-top:1px solid {INK};padding-top:12px;font-size:11.5px;line-height:1.8;color:{MUTED}">
          排序由你的 profile.yml 决定：研究问题 40%、新颖 20%、证据 18%、影响 12%、迁移 10%。每天只放 1+3 篇。<br>
          想暂停邮件：把 <span style="font-family:{MONO};font-size:10.5px">delivery.email.enabled</span> 改成 false。<br>
          {_esc(day.get("model") or "")} · {_esc(day.get("generated_at") or "")}
        </div>
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def render_email_text(day: Dict[str, Any], profile: Dict[str, Any]) -> str:
    cfg = _cfg(profile)
    lines: List[str] = [f"{day.get('date')} 口腔文献日课", ""]
    must = day.get("must_read") or {}
    deep = must.get("deep") or {}
    if must:
        lines += [
            "【精读】" + str(must.get("title_zh") or must.get("title")),
            f"{must.get('journal')} · {must.get('date')} · {must.get('design_label')}",
            f"{must.get('one_line') or ''}",
            "",
            f"问题：{deep.get('question', '')}",
            f"设计：{deep.get('design', '')}",
        ]
        for f in deep.get("findings") or []:
            lines.append(f"- {f.get('claim')}：{f.get('evidence')}")
        if deep.get("relation"):
            lines.append(f"与我：{deep.get('relation')}")
        if deep.get("limitations"):
            lines.append("局限：" + "；".join(deep["limitations"]))
        lines.append("追问：" + " / ".join(deep.get("followups") or []))
        lines += ["", f"原文：{must.get('url')}", ""]
    for i, p in enumerate(day.get("scan") or []):
        lines += [
            f"【速览 {i + 2:02d}】{p.get('title_zh') or p.get('title')}",
            f"{p.get('one_line') or ''}",
            f"对我：{p.get('so_what') or ''}（{p.get('caution') or ''}）",
            f"{p.get('url')}",
            "",
        ]
    w = day.get("weekly") or {}
    if w:
        lines += ["【本周地图】" + str(w.get("headline") or ""), ""]
        for c in w.get("clusters") or []:
            lines.append(f"- {c.get('name')}（{c.get('n')} 篇）：{c.get('insight')}")
        lines.append("")
    lines += ["——", f"网页版：{day_url(day, cfg)}", "想暂停邮件：把 config/profile.yml 里 delivery.email.enabled 改成 false"]
    return "\n".join(lines)


# ---------------------------------------------------------------- providers
def resolve_provider(cfg: Dict[str, Any]) -> Tuple[str, Dict[str, str]]:
    """Explicit provider wins; otherwise Resend, then SMTP, then none."""
    choice = str(cfg.get("provider") or "auto").lower()
    resend_key = os.environ.get("RESEND_API_KEY", "").strip()
    smtp = {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": os.environ.get("SMTP_PORT", "465").strip() or "465",
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASS", "").strip(),
    }
    has_smtp = bool(smtp["host"] and smtp["user"] and smtp["password"])
    if choice == "resend":
        return ("resend", {"key": resend_key}) if resend_key else ("none", {})
    if choice == "smtp":
        return ("smtp", smtp) if has_smtp else ("none", {})
    if resend_key:
        return "resend", {"key": resend_key}
    if has_smtp:
        return "smtp", smtp
    return "none", {}


def send_day(day: Dict[str, Any], profile: Dict[str, Any], timeout: int = 30) -> Dict[str, Any]:
    cfg = _cfg(profile)
    if not cfg.get("enabled", False):
        return {"sent": False, "reason": "disabled"}
    to = (os.environ.get("EMAIL_TO") or cfg.get("to") or "").strip()
    if not to:
        return {"sent": False, "reason": "no recipient"}
    shown = (1 if day.get("must_read") else 0) + len(day.get("scan") or [])
    if shown == 0 and not cfg.get("send_when_empty", False):
        return {"sent": False, "reason": "empty day"}

    provider, creds = resolve_provider(cfg)
    if provider == "none":
        return {"sent": False, "reason": "no credentials (RESEND_API_KEY / SMTP_*)"}

    subject = subject_for(day)
    html = render_email_html(day, profile)
    text = render_email_text(day, profile)
    sender = (os.environ.get("EMAIL_FROM") or cfg.get("from") or "onboarding@resend.dev").strip()

    if provider == "resend":
        resp = requests.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {creds['key']}", "Content-Type": "application/json"},
            json={"from": sender, "to": [to], "subject": subject, "html": html, "text": text},
            timeout=timeout,
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"Resend {resp.status_code}: {resp.text[:300]}")
        return {"sent": True, "provider": "resend", "to": to, "id": (resp.json() or {}).get("id", "")}

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    host, port = creds["host"], int(creds["port"])
    if port == 587:
        with smtplib.SMTP(host, port, timeout=timeout) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(creds["user"], creds["password"])
            smtp.send_message(msg)
    else:
        with smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context()) as smtp:
            smtp.login(creds["user"], creds["password"])
            smtp.send_message(msg)
    return {"sent": True, "provider": "smtp", "to": to}
