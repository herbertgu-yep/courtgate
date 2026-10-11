"""图形验证码生成器：零依赖 SVG 实现。

- 随机 4 位字符（剔除 0/O/1/l/I 等易混淆字符）
- 每字符随机颜色 / 旋转 / 基线偏移，加噪线与噪点
- 服务端只存文本（Redis，一次性，5 分钟过期），图片本身不含答案
"""

from __future__ import annotations

import base64
import random
import secrets
import uuid

_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉易混淆的 0/O/1/l/I
_COLORS = ["#2563eb", "#dc2626", "#16a34a", "#d97706", "#7c3aed", "#0891b2"]

WIDTH, HEIGHT = 132, 44


def generate_text(length: int = 4) -> str:
    return "".join(random.choice(_CHARS) for _ in range(length))


def render_svg(text: str) -> str:
    """把验证码文本渲染为带干扰的 SVG 图片。"""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#f8fafc"/>',
    ]
    # 噪线
    for _ in range(4):
        x1, y1 = random.randint(0, WIDTH), random.randint(0, HEIGHT)
        x2, y2 = random.randint(0, WIDTH), random.randint(0, HEIGHT)
        color = random.choice(_COLORS)
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.5" opacity="0.5"/>'
        )
    # 噪点
    for _ in range(30):
        cx, cy = random.randint(0, WIDTH), random.randint(0, HEIGHT)
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{random.randint(1, 2)}" fill="{random.choice(_COLORS)}" opacity="0.4"/>'
        )
    # 字符：随机旋转 / 基线 / 颜色 / 字号
    step = (WIDTH - 24) // len(text)
    for i, ch in enumerate(text):
        x = 16 + i * step + random.randint(-4, 4)
        y = HEIGHT // 2 + random.randint(-4, 8)
        rotate = random.randint(-25, 25)
        size = random.randint(24, 30)
        color = random.choice(_COLORS)
        parts.append(
            f'<text x="{x}" y="{y}" font-family="Georgia,serif" font-size="{size}" '
            f'font-weight="bold" fill="{color}" '
            f'transform="rotate({rotate} {x} {y})">{ch}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def generate() -> tuple[str, str, str]:
    """生成一对验证码。返回 (captcha_id, 文本, data-uri 图片)。"""
    text = generate_text()
    captcha_id = uuid.uuid4().hex
    svg = render_svg(text)
    b64 = base64.b64encode(svg.encode()).decode()
    return captcha_id, text, f"data:image/svg+xml;base64,{b64}"


def new_captcha_token() -> str:
    return secrets.token_hex(8)
