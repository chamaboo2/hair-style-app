import base64
import hashlib
import html
import importlib.util
import io
import json
import logging
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas


logger = logging.getLogger(__name__)


RESULT_STATE_KEYS = (
    "styles",
    "selected_style_index",
    "after_image",
    "selected_style",
    "style_sheet_png",
    "style_sheet_pdf",
)

# 将来、利用料金やクレジット数を案内する場合は True に変更します。
# 無料提供中は False のままにすると、料金案内は画面に表示されません。
SHOW_USAGE_COST = False
PROPOSAL_COST_TEXT = "使用クレジット：1"
IMAGE_COST_TEXT = "使用クレジット：1"
SHEET_COST_TEXT = "使用クレジット：3"


def restart_with_same_photo():
    """Keep the current photo and return to hairstyle suggestions."""
    for state_key in RESULT_STATE_KEYS:
        st.session_state.pop(state_key, None)


def restart_with_new_photo():
    """Clear the current flow and return to the first screen."""
    st.session_state.clear()


def show_usage_cost(message):
    if SHOW_USAGE_COST:
        st.markdown(f'<div class="cost-note">{html.escape(message)}</div>', unsafe_allow_html=True)


def select_suggestion(index):
    st.session_state.selected_style_index = index
    for state_key in ("after_image", "selected_style", "style_sheet_png", "style_sheet_pdf"):
        st.session_state.pop(state_key, None)


def render_step(step, title):
    progress = round(step / 7 * 100)
    st.markdown(
        f'<div class="step-header"><div class="step-meta">STEP {step} / 7</div>'
        f'<div class="step-progress"><span style="width:{progress}%"></span></div>'
        f'<h2>{html.escape(title)}</h2></div>',
        unsafe_allow_html=True,
    )


def render_copy_button(order_text):
    safe_text = json.dumps(order_text, ensure_ascii=False)
    components.html(
        f'''<!doctype html><html><head><meta charset="utf-8"><style>
        body{{margin:0;background:transparent;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
        button{{width:100%;height:46px;border:1px solid #87515c;border-radius:999px;background:#43383a;color:#fff;font-size:15px;font-weight:700;cursor:pointer}}
        button:active{{transform:scale(.99)}}
        </style></head><body><button id="copy">オーダー文をコピー</button><script>
        const text={safe_text}; const button=document.getElementById('copy');
        button.addEventListener('click', async () => {{
          try {{ await navigator.clipboard.writeText(text); }}
          catch (e) {{ const area=document.createElement('textarea'); area.value=text; document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove(); }}
          button.textContent='コピーしました ✓'; setTimeout(() => button.textContent='オーダー文をコピー', 1800);
        }});
        </script></body></html>''',
        height=52,
    )


st.set_page_config(page_title="美容師さんお願いシート", page_icon="🪞", layout="centered")

st.markdown("""
<style>
:root {
    --rose: #a86773;
    --rose-dark: #87515c;
    --rose-pale: #f5e9eb;
    --ivory: #fdfaf7;
    --ink: #3d3436;
    --muted: #62575a;
    --line: #e8dadd;
    --radius: 16px;
    --button-height: 3rem;
}
.stApp {
    background:
        radial-gradient(circle at 100% 0%, rgba(232, 205, 211, .38), transparent 34rem),
        linear-gradient(180deg, #fffdfb 0%, var(--ivory) 100%);
    color: var(--ink);
}
.stApp p,
.stApp li,
.stApp label,
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stWidgetLabel"],
.stApp [data-testid="stRadio"] label,
.stApp [data-testid="stCheckbox"] label,
.stApp [data-testid="stFileUploader"] small,
.stApp [data-testid="stAlert"] {
    color: var(--ink) !important;
}
.stApp div[role="radiogroup"] {
    gap: .55rem;
}
.stApp div[role="radiogroup"] > label {
    padding: .68rem .85rem !important;
    border: 1px solid var(--line) !important;
    border-radius: 13px !important;
    background: rgba(255, 255, 255, .94) !important;
}
.stApp div[role="radiogroup"] > label:has(input:checked) {
    border-color: var(--rose) !important;
    background: var(--rose-pale) !important;
    box-shadow: 0 3px 10px rgba(135, 81, 92, .08);
}
.stApp div[role="radiogroup"] > label p,
.stApp div[role="radiogroup"] > label span,
.stApp [data-testid="stRadio"] label p,
.stApp [data-testid="stRadio"] label span {
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
    opacity: 1 !important;
}
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stCaptionContainer"] p,
.stApp .stCaption {
    color: var(--muted) !important;
}
.stApp input,
.stApp textarea,
.stApp [data-baseweb="select"] span,
.stApp [data-baseweb="select"] div {
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}
.stApp input::placeholder,
.stApp textarea::placeholder {
    color: #9b8d90 !important;
    -webkit-text-fill-color: #9b8d90 !important;
    opacity: 1;
}
/* プルダウンをOS・ブラウザの配色に左右されず読みやすくする */
[data-baseweb="select"] > div {
    background: #ffffff !important;
    color: var(--ink) !important;
}
[data-baseweb="popover"],
[data-baseweb="popover"] ul[role="listbox"] {
    background: #ffffff !important;
}
[data-baseweb="popover"] li[role="option"] {
    background: #ffffff !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}
[data-baseweb="popover"] li[role="option"] * {
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}
[data-baseweb="popover"] li[role="option"][aria-selected="true"] {
    background: var(--rose-dark) !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
[data-baseweb="popover"] li[role="option"][aria-selected="true"] * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
.block-container {
    max-width: 720px;
    padding-top: 1.1rem;
    padding-bottom: 4rem;
}
.hero {
    padding: 1.9rem 1.35rem 1.55rem;
    margin: 0 0 1.5rem;
    text-align: center;
    border: 1px solid rgba(168, 103, 115, .18);
    border-radius: 24px;
    background: rgba(255, 255, 255, .72);
    box-shadow: 0 12px 34px rgba(93, 62, 68, .07);
}
.hero-mark {
    width: 42px;
    height: 2px;
    margin: 0 auto 1rem;
    background: var(--rose);
}
.hero-illustration {
    display: block;
    width: 108px;
    height: 150px;
    margin: -0.35rem auto .75rem;
    object-fit: contain;
    filter: drop-shadow(0 8px 12px rgba(93, 62, 68, .12));
}
.hero-kicker {
    margin: 0 0 .55rem;
    color: var(--rose);
    font-size: .72rem;
    letter-spacing: .18em;
    font-weight: 700;
}
.hero h1 {
    margin: 0;
    color: #43383a;
    font-size: clamp(1.45rem, 6.7vw, 2.45rem);
    line-height: 1.3;
    letter-spacing: .03em;
    white-space: nowrap;
}
.hero p {
    margin: .8rem auto 0;
    max-width: 31rem;
    color: var(--muted);
    font-size: .95rem;
    line-height: 1.8;
}
.hero-feature {
    margin-top: .9rem;
    color: var(--rose-dark);
    font-size: .86rem;
    font-weight: 700;
    line-height: 1.7;
}
.hero-pills {
    display: flex;
    justify-content: center;
    flex-wrap: wrap;
    gap: .4rem;
    margin-top: .8rem;
}
.hero-pills span {
    padding: .3rem .65rem;
    border: 1px solid #e2cbd0;
    border-radius: 999px;
    background: #fffaf9;
    color: var(--rose-dark);
    font-size: .72rem;
    font-weight: 700;
}
.privacy-note,
.cost-note {
    margin: .65rem 0 1rem;
    padding: .8rem .9rem;
    border: 1px solid #e3d2d5;
    border-radius: 14px;
    background: rgba(255, 255, 255, .78);
    color: #5f5255;
    font-size: .84rem;
    line-height: 1.65;
}
.cost-note {
    margin-bottom: .55rem;
    border-color: #d8b7be;
    background: var(--rose-pale);
    color: var(--rose-dark);
    font-weight: 700;
    text-align: center;
}
.style-card {
    margin: .75rem 0;
    padding: 1rem;
    border: 1px solid var(--line);
    border-radius: 18px;
    background: rgba(255, 255, 255, .86);
    box-shadow: 0 5px 16px rgba(93, 62, 68, .05);
}
.style-card.selected {
    border: 2px solid var(--rose);
    background: #fbf1f3;
    box-shadow: 0 7px 20px rgba(135, 81, 92, .11);
}
.selected-badge {
    display: inline-block;
    margin-bottom: .55rem;
    padding: .2rem .55rem;
    border-radius: 999px;
    background: var(--rose);
    color: #ffffff;
    font-size: .72rem;
    font-weight: 800;
}
.style-card-title {
    margin-bottom: .8rem;
    color: #493b3e;
    font-size: 1.05rem;
    font-weight: 800;
}
.style-card-grid {
    display: grid;
    grid-template-columns: 4.3rem 1fr;
    gap: .48rem .7rem;
    align-items: start;
    font-size: .91rem;
    line-height: 1.55;
}
.style-card-label {
    color: var(--rose-dark);
    font-weight: 700;
}
.style-card-value {color: var(--ink);}
.style-reason {
    margin-top: .85rem;
    padding: .78rem .85rem;
    border-left: 4px solid var(--rose);
    border-radius: 10px;
    background: #f7e9ec;
    color: var(--ink);
    font-size: .88rem;
    line-height: 1.65;
}
.style-reason strong {
    display: block;
    margin-bottom: .2rem;
    color: var(--rose-dark);
}
.selected-summary {
    margin: .6rem 0;
    padding: .75rem .85rem;
    border: 1px solid #d8b7be;
    border-radius: 13px;
    background: var(--rose-pale);
    color: var(--rose-dark);
    font-size: .9rem;
    font-weight: 800;
    text-align: center;
}
.before-after {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: .65rem;
    width: 100%;
    max-width: 560px;
    margin: .5rem auto 1rem;
}
.before-after figure {margin: 0; min-width: 0;}
.before-after img {
    display: block;
    width: 100%;
    aspect-ratio: 3 / 4;
    object-fit: cover;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: #ffffff;
}
.before-after figcaption {
    margin-top: .35rem;
    color: var(--muted);
    font-size: .8rem;
    text-align: center;
}
.step-header {
    margin: 2rem 0 .85rem;
}
.step-meta {
    margin-bottom: .32rem;
    color: var(--rose-dark);
    font-size: .7rem;
    font-weight: 800;
    letter-spacing: .1em;
}
.step-progress {
    width: 100%;
    height: 3px;
    margin-bottom: .65rem;
    overflow: hidden;
    border-radius: 999px;
    background: #eadde0;
}
.step-progress span {
    display: block;
    height: 100%;
    border-radius: inherit;
    background: var(--rose);
}
.step-header h2,
h2 {
    color: #4b3e41 !important;
    font-size: clamp(1.25rem, 4.8vw, 1.65rem) !important;
    line-height: 1.35 !important;
    margin: 0 !important;
    font-weight: 750 !important;
    word-break: keep-all;
    overflow-wrap: normal;
}
h3 {color: #4b3e41 !important;}
label, [data-testid="stWidgetLabel"] {color: #514548 !important;}
/* 補助操作：白地の控えめな枠線ボタン */
div.stButton > button {
    width: 100%;
    min-height: var(--button-height);
    border: 1px solid #b98a93 !important;
    border-radius: 999px;
    background: #fffdfb !important;
    color: var(--rose-dark) !important;
    font-weight: 700;
    box-shadow: none;
}
div.stButton > button p,
div.stButton > button span {
    color: var(--rose-dark) !important;
    -webkit-text-fill-color: var(--rose-dark) !important;
}
div.stButton > button:hover {
    background: var(--rose-pale) !important;
    border-color: var(--rose-dark) !important;
}
/* メイン操作：くすみピンク＋白文字 */
div.stButton > button[kind="primary"] {
    min-height: 3.2rem;
    background: var(--rose) !important;
    border-color: var(--rose) !important;
    color: #ffffff !important;
    box-shadow: 0 7px 18px rgba(135, 81, 92, .18);
}
div.stButton > button[kind="primary"] p,
div.stButton > button[kind="primary"] span {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
div.stButton > button[kind="primary"]:hover {
    background: var(--rose-dark) !important;
}
div.stButton > button:disabled {
    background: #eee4e6 !important;
    border-color: #d8c6ca !important;
    color: #675b5e !important;
    opacity: 1 !important;
}
div.stButton > button:disabled * {
    color: #675b5e !important;
    -webkit-text-fill-color: #675b5e !important;
}
/* 保存操作：濃色＋白文字 */
div.stDownloadButton > button {
    min-height: var(--button-height);
    border-color: #43383a !important;
    border-radius: 999px;
    background: #43383a !important;
    color: #ffffff !important;
}
div.stDownloadButton > button p,
div.stDownloadButton > button span {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}
[data-testid="stFileUploader"] button,
[data-testid="stCameraInput"] button {
    border-color: var(--rose) !important;
    color: var(--rose-dark) !important;
    background: white !important;
}
[data-testid="stFileUploader"] button *,
[data-testid="stCameraInput"] button * {
    color: var(--rose-dark) !important;
    -webkit-text-fill-color: var(--rose-dark) !important;
}
[data-testid="stFileUploader"] {
    border: 1px dashed #d7b8be;
    border-radius: 18px;
    background: rgba(255, 255, 255, .76);
    padding: .25rem;
}
[data-baseweb="select"] > div,
[data-baseweb="input"] > div,
[data-testid="stTextInputRootElement"],
[data-testid="stTextArea"] textarea {
    border-color: var(--line) !important;
    border-radius: 13px !important;
    background: rgba(255, 255, 255, .9) !important;
}
[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--line) !important;
    border-radius: 18px !important;
    background: rgba(255, 255, 255, .72);
}
.order-card {
    margin: .45rem 0 .65rem;
    padding: 1rem;
    border: 1px solid #d8c6ca;
    border-radius: var(--radius);
    background: rgba(255, 255, 255, .88);
    color: var(--ink);
    font-size: .94rem;
    line-height: 1.8;
    white-space: pre-wrap;
    box-shadow: 0 5px 16px rgba(93, 62, 68, .05);
}
.zoom-sheet {
    width: 100%;
    max-height: 72vh;
    overflow: auto;
    padding: .5rem;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: #ffffff;
    -webkit-overflow-scrolling: touch;
}
.zoom-sheet img {
    display: block;
    width: 1000px;
    max-width: none;
    height: auto;
}
[data-testid="stAlert"] {border-radius: 16px;}
hr {border-color: var(--line) !important;}
.stCaption, [data-testid="stCaptionContainer"] {color: var(--muted) !important;}
@media (max-width: 640px) {
    .block-container {padding-left: 1rem; padding-right: 1rem; padding-bottom: 3rem;}
    .hero {padding: 1.55rem 1rem 1.3rem; border-radius: 20px;}
    .hero-illustration {width: 92px; height: 132px;}
    .hero h1 {font-size: clamp(1.35rem, 6.5vw, 1.75rem); letter-spacing: 0;}
    .style-card {padding: .9rem;}
    .step-header {margin-top: 1.7rem;}
    .step-header h2, h2 {
        font-size: clamp(1.05rem, 4.65vw, 1.3rem) !important;
        white-space: nowrap;
    }
    .before-after {grid-template-columns: 48% 48%; justify-content: space-between; gap: 0;}
    .before-after img {border-radius: 12px;}
}
</style>
""", unsafe_allow_html=True)

hero_image_path = Path(__file__).resolve().parent / "job_biyoushi_original.png"
hero_image_html = ""
if hero_image_path.exists():
    hero_image_base64 = base64.b64encode(hero_image_path.read_bytes()).decode("ascii")
    hero_image_html = (
        f'<img class="hero-illustration" '
        f'src="data:image/png;base64,{hero_image_base64}" alt="美容師さんのイラスト">'
    )

st.markdown(f"""
<section class="hero">
  <div class="hero-mark"></div>
  {hero_image_html}
  <p class="hero-kicker">HAIR STYLE CONSULTATION</p>
  <h1>美容師さんお願いシート</h1>
  <p>似合いそうな髪型を試すだけでなく、完成イメージとオーダー内容を、美容師さんにそのまま見せられる一枚にまとめます。</p>
  <div class="hero-feature">髪型選びから、美容院で見せるお願いシートまで</div>
  <div class="hero-pills"><span>似合う髪型を3案</span><span>完成イメージ</span><span>PNG・PDF保存</span></div>
</section>
""", unsafe_allow_html=True)


class HairStyle(BaseModel):
    title: str
    haircut: str
    bangs: str
    tone: str
    color: str
    reason: str
    order: str


class HairStyleSuggestions(BaseModel):
    styles: list[HairStyle] = Field(min_length=3, max_length=3)


def get_client():
    try:
        return OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
    except KeyError:
        st.error("OPENAI_API_KEYが設定されていません。StreamlitのSecretsを確認してください。")
        st.stop()


def normalized_image_bytes(uploaded_file):
    image = Image.open(uploaded_file).convert("RGB")
    image.thumbnail((1536, 1536))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=92)
    buffer.seek(0)
    buffer.name = "face.jpg"
    return image, buffer


def propose_styles(client, image_buffer, choices):
    encoded = base64.b64encode(image_buffer.getvalue()).decode("utf-8")
    prompt = f"""
あなたは実務経験のある日本の美容師です。写真と希望条件から、現実に美容室で再現できる髪型・髪色を3案提案してください。
希望条件: {json.dumps(choices, ensure_ascii=False)}
写真から年齢、人種、健康状態などを断定しないでください。顔立ちの優劣を評価せず、髪と顔まわりの見た目のバランス、希望条件、再現性を中心に考えてください。
異なる方向性の提案を必ず3件作ってください。おまかせ項目は写真との調和を考えて具体化してください。
titleは短い名称、haircutは長さ・形・レイヤー等、bangsは前髪、toneは数字を含むトーン、colorは髪色、reasonは似合いそうな理由を60字以内、orderは美容師へそのまま見せられる具体的なオーダー文にしてください。
"""
    response = client.responses.parse(
        model="gpt-5-mini",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}"},
            ],
        }],
        text_format=HairStyleSuggestions,
    )
    if response.output_parsed is None:
        raise ValueError("提案データを取得できませんでした。")
    return [style.model_dump() for style in response.output_parsed.styles]


def edit_hairstyle(client, image_buffer, style):
    prompt = f"""
Edit this exact person's photograph with high identity fidelity. Change only the hair as much as technically possible.
Keep the same eyes, eyebrows, nose, mouth, ears, face shape, skin texture and tone, expression, apparent age, body, clothing, pose, camera angle, lighting, and background.
Do not beautify, retouch, slim the face, enlarge the eyes, smooth the skin, change makeup, or turn the person into someone else.
Create a natural, photorealistic Japanese hair-salon result with believable hairline, strands, volume, shadows, and highlights.
Requested haircut: {style['haircut']}.
Bangs: {style['bangs']}.
Hair color: {style['tone']}、{style['color']}.
Preserve everything outside the hair region.
"""
    image_buffer.seek(0)
    result = client.images.edit(
        model="gpt-image-1.5",
        image=image_buffer,
        prompt=prompt,
        input_fidelity="high",
        quality="high",
        output_format="jpeg",
        size="1024x1536",
    )
    return base64.b64decode(result.data[0].b64_json)


def generate_detail_views(client, original_buffer, after_bytes, style):
    """同じスタイルの横・耳まわり・後ろ姿を1枚の3分割画像で生成する。"""
    original_buffer.seek(0)
    after_buffer = io.BytesIO(after_bytes)
    after_buffer.name = "finished_style.jpg"
    prompt = f"""
Create one clean photorealistic hair-salon reference contact sheet with exactly three equal vertical panels and no text, logos, frames, captions, or decorations.
Use the first image as the identity reference and the second image as the exact finished hairstyle reference.
Keep the same person and the exact same haircut, hair length, layers, bangs, color, tone, texture, and finish in every panel.
Do not beautify, retouch, change age, body, skin, makeup, clothing, or identity.
Panel 1: three-quarter side view with the hair naturally tucked behind one ear so the inner color and face-framing layers are visible.
Panel 2: close-up detail of the ear area, hairline, inner color, strands, and layering.
Panel 3: centered back view showing the full haircut shape, length, layers, and color placement; face must not be visible.
Use neutral salon lighting and a plain warm-white background.
Requested style: {style['haircut']}; bangs: {style['bangs']}; color: {style['tone']} {style['color']}.
"""
    result = client.images.edit(
        model="gpt-image-1.5",
        image=[original_buffer, after_buffer],
        prompt=prompt,
        input_fidelity="high",
        quality="high",
        output_format="jpeg",
        size="1536x1024",
    )
    return base64.b64decode(result.data[0].b64_json)


def japanese_font_path():
    spec = importlib.util.find_spec("japanize_matplotlib")
    if spec is None or spec.origin is None:
        raise FileNotFoundError("日本語フォント用パッケージが見つかりません。")
    font_dir = Path(spec.origin).resolve().parent / "fonts"
    candidates = list(font_dir.glob("*.ttf"))
    if not candidates:
        raise FileNotFoundError("日本語フォントが見つかりません。")
    return str(candidates[0])


def fit_crop(image, width, height):
    image = image.convert("RGB")
    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def split_detail_views(detail_bytes):
    contact = Image.open(io.BytesIO(detail_bytes)).convert("RGB")
    panel_width = contact.width // 3
    return [
        contact.crop((i * panel_width, 0, contact.width if i == 2 else (i + 1) * panel_width, contact.height))
        for i in range(3)
    ]


def wrapped_lines(draw, text, font, max_width):
    lines = []
    current = ""
    for char in str(text):
        trial = current + char
        if current and draw.textlength(trial, font=font) > max_width:
            lines.append(current)
            current = char
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def draw_wrapped(draw, text, xy, font, fill, max_width, line_gap=10, max_lines=None):
    x, y = xy
    lines = wrapped_lines(draw, text, font, max_width)
    if max_lines:
        lines = lines[:max_lines]
    line_height = font.size + line_gap
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return y


def draw_bullets(draw, items, x, y, font, fill, max_width, bottom):
    for item in items:
        if y + font.size >= bottom:
            break
        draw.ellipse((x, y + 12, x + 10, y + 22), fill=fill)
        y = draw_wrapped(draw, item, (x + 24, y), font, fill, max_width - 24, 9, 3) + 12
    return y


def create_style_sheet(after_bytes, detail_bytes, style):
    navy = "#132D4F"
    ink = "#202A36"
    paper = "#FAF9F6"
    sheet = Image.new("RGB", (1800, 1350), paper)
    draw = ImageDraw.Draw(sheet)
    font_path = japanese_font_path()
    title_font = ImageFont.truetype(font_path, 48)
    subtitle_font = ImageFont.truetype(font_path, 28)
    section_font = ImageFont.truetype(font_path, 28)
    body_font = ImageFont.truetype(font_path, 21)
    small_font = ImageFont.truetype(font_path, 18)

    draw.text((55, 35), style["title"], font=title_font, fill=navy)
    draw.text((60, 92), f"{style['tone']}・{style['color']}", font=subtitle_font, fill=ink)

    front = fit_crop(Image.open(io.BytesIO(after_bytes)), 690, 670)
    side, closeup, back = split_detail_views(detail_bytes)
    sheet.paste(front, (0, 140))
    sheet.paste(fit_crop(side, 520, 330), (695, 140))
    sheet.paste(fit_crop(closeup, 520, 330), (695, 480))
    sheet.paste(fit_crop(back, 630, 400), (585, 825))

    def label(x, y, text):
        box_w = max(110, int(draw.textlength(text, font=small_font)) + 40)
        draw.rounded_rectangle((x, y, x + box_w, y + 44), radius=4, fill=navy)
        draw.text((x + 18, y + 9), text, font=small_font, fill="white")

    label(20, 752, "正面")
    label(715, 426, "耳かけ")
    label(715, 766, "耳まわり")
    label(605, 1168, "後ろ姿")

    draw.rounded_rectangle((25, 840, 555, 1305), radius=22, outline="#7F8C9B", width=2, fill="#FFFDFC")
    draw.text((55, 870), "Point", font=section_font, fill=navy)
    point = f"{style['reason']}。{style['haircut']}をベースに、{style['color']}の色味が自然に見えるデザインです。"
    draw_wrapped(draw, point, (55, 925), body_font, ink, 465, 13, 9)

    panel_x = 1250
    panel_w = 510
    sections = [
        ("スタイル概要", [style["haircut"], f"前髪：{style['bangs']}", f"カラー：{style['tone']}・{style['color']}"]),
        ("見せたい印象", [style["reason"]]),
        ("カラーの考え方", [f"明るさは{style['tone']}を目安", f"色味は{style['color']}", "現在の髪色や髪質に合わせて美容師と微調整"]),
    ]
    top = 145
    for heading, bullets in sections:
        draw.text((panel_x + 20, top), heading, font=section_font, fill=navy)
        top += 48
        top = draw_bullets(draw, bullets, panel_x + 22, top, body_font, ink, panel_w - 45, top + 205)
        top += 10
        draw.line((panel_x + 10, top, panel_x + panel_w, top), fill="#9AA6B4", width=2)
        top += 22

    order_items = [part.strip() for part in style["order"].replace("！", "。").split("。") if part.strip()]
    draw.rounded_rectangle((panel_x, 925, 1770, 1305), radius=20, outline=navy, width=2, fill="#FFFDFC")
    draw.rounded_rectangle((panel_x + 65, 945, 1705, 990), radius=6, fill=navy)
    order_title = "美容師さんにお願いしたいこと"
    title_width = draw.textlength(order_title, font=small_font)
    draw.text((panel_x + 260 - title_width / 2, 955), order_title, font=small_font, fill="white")
    draw_bullets(draw, order_items, panel_x + 28, 1015, body_font, ink, panel_w - 55, 1280)
    return sheet


def image_to_png_bytes(image):
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def image_to_pdf_bytes(image):
    output = io.BytesIO()
    width, height = image.size
    pdf = pdf_canvas.Canvas(output, pagesize=(width, height))
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="JPEG", quality=95)
    image_buffer.seek(0)
    pdf.drawImage(ImageReader(image_buffer), 0, 0, width=width, height=height)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


render_step(1, "顔写真を用意")
camera_photo = st.camera_input("顔写真を撮る", key="camera_photo")
selected_photo = None
if camera_photo is None:
    with st.expander("端末にある写真を使う"):
        selected_photo = st.file_uploader(
            "写真を1枚選ぶ",
            type=["jpg", "jpeg", "png"],
            label_visibility="collapsed",
            key="selected_photo",
        )
uploaded = camera_photo or selected_photo
st.caption("顔と髪全体が入るように、明るい場所で撮影してください。写真は本アプリには保存されません。")
st.markdown(
    '<div class="privacy-note"><strong>写真の取り扱い</strong><br>'
    '写真は髪型の提案と完成イメージの生成にだけ使用し、OpenAI APIへ一時的に送信します。'
    '本アプリやSupabaseには保存しません。</div>',
    unsafe_allow_html=True,
)

if uploaded:
    try:
        current_photo_hash = hashlib.sha256(uploaded.getvalue()).hexdigest()
        if st.session_state.get("photo_hash") != current_photo_hash:
            st.session_state.photo_hash = current_photo_hash
            for state_key in RESULT_STATE_KEYS:
                st.session_state.pop(state_key, None)
        original_image, image_buffer = normalized_image_bytes(uploaded)
        st.image(original_image, caption="使用する写真", use_container_width=True)
    except Exception:
        st.error("写真を読み込めませんでした。撮り直すか、別の写真を選んでください。")
        st.stop()

    render_step(2, "おすすめを見る")
    style_category = st.selectbox(
        "希望するスタイル",
        ["レディース", "メンズ"],
        help="選んだスタイルに合わせて、雰囲気・長さ・前髪の候補が変わります。",
        on_change=restart_with_same_photo,
    )
    if style_category == "レディース":
        mood_options = ["おまかせ", "かわいい", "きれい", "上品", "かっこいい", "ナチュラル"]
        length_options = ["おまかせ", "ショート", "ボブ", "ミディアム", "ロング"]
        bangs_options = ["おまかせ", "あり", "なし"]
    else:
        mood_options = ["おまかせ", "清潔感", "爽やか", "かっこいい", "大人っぽい", "ナチュラル"]
        length_options = ["おまかせ", "ベリーショート", "ショート", "ミディアム", "ロング"]
        bangs_options = ["おまかせ", "下ろす", "上げる", "なし"]

    mood = "おまかせ"
    length = "おまかせ"
    bangs = "おまかせ"
    color = "おまかせ"
    custom_color = ""
    tone = "おまかせ"
    with st.expander("希望があれば指定する（任意）"):
        mood = st.selectbox("なりたい雰囲気", mood_options, key=f"mood_{style_category}")
        length = st.selectbox("髪の長さ", length_options, key=f"length_{style_category}")
        bangs = st.selectbox("前髪", bangs_options, key=f"bangs_{style_category}")
        color = st.selectbox("髪色", ["おまかせ", "黒", "ブラウン", "ベージュ", "ピンク", "ブルー", "その他"])
        if color == "その他":
            custom_color = st.text_input("希望する髪色", placeholder="例：ブルーグレージュ")
        if color != "おまかせ":
            tone = st.selectbox(
                "明るさ",
                ["おまかせ"] + [f"{number}トーン" for number in range(1, 16)],
            )

    choices = {
        "スタイル区分": style_category,
        "雰囲気": mood,
        "長さ": length,
        "前髪": bangs,
        "髪色": custom_color or color,
        "明るさ": tone,
    }
    st.caption("ボタンを押すと、写真が提案のためOpenAI APIへ送信されます。")

    show_usage_cost(PROPOSAL_COST_TEXT)
    if st.button("おすすめを3案見る", type="primary"):
        with st.spinner("似合いそうなスタイルを考えています…"):
            try:
                st.session_state.styles = propose_styles(get_client(), image_buffer, choices)
                st.session_state.selected_style_index = 0
                st.session_state.pop("after_image", None)
                st.session_state.pop("style_sheet_png", None)
                st.session_state.pop("style_sheet_pdf", None)
            except Exception as exc:
                logger.exception("Failed to propose hairstyles")
                st.error("提案を作成できませんでした。少し待ってから、もう一度お試しください。")

    if "styles" in st.session_state:
        render_step(3, "気になる案を選ぶ")
        st.caption("各カードの「この案を選ぶ」をタップしてください。案1〜3のどれでも選べます。")
        selected_index = st.session_state.get("selected_style_index", 0)
        if selected_index not in range(len(st.session_state.styles)):
            selected_index = 0
            st.session_state.selected_style_index = 0
        selected_style = st.session_state.styles[selected_index]

        for index, style in enumerate(st.session_state.styles, 1):
            card_class = "style-card selected" if index - 1 == selected_index else "style-card"
            selected_badge = '<div class="selected-badge">✓ 現在選択中</div>' if index - 1 == selected_index else ""
            title = html.escape(f"案{index}｜{style['title']}")
            haircut = html.escape(style["haircut"])
            bangs_text = html.escape(style["bangs"])
            color_text = html.escape(f"{style['tone']}・{style['color']}")
            reason = html.escape(style["reason"])
            card_html = (
                f'<article class="{card_class}">{selected_badge}'
                f'<div class="style-card-title">{title}</div>'
                f'<div class="style-card-grid">'
                f'<div class="style-card-label">髪型</div><div class="style-card-value">{haircut}</div>'
                f'<div class="style-card-label">前髪</div><div class="style-card-value">{bangs_text}</div>'
                f'<div class="style-card-label">カラー</div><div class="style-card-value">{color_text}</div>'
                f'</div><div class="style-reason"><strong>この案がおすすめな理由</strong>{reason}</div>'
                f'</article>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

            if index - 1 == selected_index:
                st.button(
                    f"✓ 案{index}を選択中",
                    key=f"select_style_{index}",
                    disabled=True,
                    use_container_width=True,
                )
            else:
                st.button(
                    f"案{index}を選ぶ",
                    key=f"select_style_{index}",
                    on_click=select_suggestion,
                    args=(index - 1,),
                    use_container_width=True,
                )

        selected_title = html.escape(f"案{selected_index + 1}｜{selected_style['title']}")
        st.markdown(
            f'<div class="selected-summary">現在選択中：{selected_title}<br>下のボタンでこの案を写真に反映します</div>',
            unsafe_allow_html=True,
        )
        show_usage_cost(IMAGE_COST_TEXT)
        if st.button(f"選択中の案{selected_index + 1}をこの写真で試す", type="primary"):
            with st.spinner("完成イメージを生成しています。しばらくお待ちください…"):
                try:
                    st.session_state.after_image = edit_hairstyle(get_client(), image_buffer, selected_style)
                    st.session_state.selected_style = selected_style
                    st.session_state.pop("style_sheet_png", None)
                    st.session_state.pop("style_sheet_pdf", None)
                except Exception as exc:
                    logger.exception("Failed to generate hairstyle image")
                    st.error("画像を生成できませんでした。少し待ってから、もう一度お試しください。")

    if "after_image" in st.session_state:
        render_step(4, "Before / After")
        before_base64 = base64.b64encode(image_buffer.getvalue()).decode("ascii")
        after_base64 = base64.b64encode(st.session_state.after_image).decode("ascii")
        comparison_html = (
            f'<div class="before-after">'
            f'<figure><img src="data:image/jpeg;base64,{before_base64}" alt="元写真"><figcaption>Before</figcaption></figure>'
            f'<figure><img src="data:image/jpeg;base64,{after_base64}" alt="生成後の写真"><figcaption>After</figcaption></figure>'
            f'</div>'
        )
        st.markdown(comparison_html, unsafe_allow_html=True)
        st.download_button("完成画像を保存", st.session_state.after_image, "hair-style-after.jpg", "image/jpeg", use_container_width=True)

        render_step(5, "美容師さん向けオーダー文")
        st.caption("このまま美容師さんに見せたり、LINEや予約フォームへ貼り付けたりできます。")
        order_text = st.session_state.selected_style["order"]
        st.markdown(
            f'<div class="order-card">{html.escape(order_text)}</div>',
            unsafe_allow_html=True,
        )
        render_copy_button(order_text)

        render_step(6, "お願いシートを作る")
        st.caption("正面・耳かけ・耳まわり・後ろ姿とオーダー内容を1枚にまとめます。追加の画像生成処理を行います。")
        show_usage_cost(SHEET_COST_TEXT)
        if st.button("美容師さんお願いシートを作る", type="primary"):
            with st.spinner("横・耳まわり・後ろ姿を生成し、スタイルシートを作っています…"):
                try:
                    detail_bytes = generate_detail_views(
                        get_client(), image_buffer, st.session_state.after_image, st.session_state.selected_style
                    )
                    style_sheet = create_style_sheet(
                        st.session_state.after_image, detail_bytes, st.session_state.selected_style
                    )
                    st.session_state.style_sheet_png = image_to_png_bytes(style_sheet)
                    st.session_state.style_sheet_pdf = image_to_pdf_bytes(style_sheet)
                except Exception as exc:
                    logger.exception("Failed to create stylist request sheet")
                    st.error("お願いシートを作成できませんでした。少し待ってから、もう一度お試しください。")

        if "style_sheet_png" in st.session_state:
            st.image(st.session_state.style_sheet_png, caption="美容師向けスタイルシート", use_container_width=True)
            with st.expander("🔍 拡大して見る"):
                sheet_base64 = base64.b64encode(st.session_state.style_sheet_png).decode("ascii")
                st.caption("画像を左右に動かして、細部を確認できます。")
                st.markdown(
                    f'<div class="zoom-sheet"><img src="data:image/png;base64,{sheet_base64}" '
                    f'alt="美容師向けスタイルシートの拡大表示"></div>',
                    unsafe_allow_html=True,
                )
            download_left, download_right = st.columns(2)
            with download_left:
                st.download_button(
                    "PNGで保存", st.session_state.style_sheet_png, "hair-style-sheet.png", "image/png",
                    use_container_width=True
                )
            with download_right:
                st.download_button(
                    "PDFで保存", st.session_state.style_sheet_pdf, "hair-style-sheet.pdf", "application/pdf",
                    use_container_width=True
                )

        render_step(7, "もう一度作る")
        retry_left, retry_right = st.columns(2)
        with retry_left:
            st.button(
                "同じ写真で別の案を見る",
                on_click=restart_with_same_photo,
                use_container_width=True,
            )
        with retry_right:
            st.button(
                "新しい写真で最初から",
                on_click=restart_with_new_photo,
                use_container_width=True,
            )
        st.caption("「新しい写真で最初から」を押すと、トップ画面に戻り、撮影からやり直せます。")
else:
    st.info("最初にカメラで顔写真を撮影してください。")

st.divider()
st.caption("生成画像は参考イメージです。髪質や現在の髪の状態により、実際の仕上がりとは異なる場合があります。")
