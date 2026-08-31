import base64
import io
import json
from pathlib import Path

import streamlit as st
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdf_canvas


st.set_page_config(page_title="美容師さんお願いシート", page_icon="🪞", layout="centered")

st.markdown("""
<style>
:root {
    --rose: #a86773;
    --rose-dark: #87515c;
    --rose-pale: #f5e9eb;
    --ivory: #fdfaf7;
    --ink: #3d3436;
    --muted: #7a6d70;
    --line: #e8dadd;
}
.stApp {
    background:
        radial-gradient(circle at 100% 0%, rgba(232, 205, 211, .38), transparent 34rem),
        linear-gradient(180deg, #fffdfb 0%, var(--ivory) 100%);
    color: var(--ink);
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
    font-size: clamp(1.75rem, 8vw, 2.45rem);
    line-height: 1.3;
    letter-spacing: .03em;
}
.hero p {
    margin: .8rem auto 0;
    max-width: 31rem;
    color: var(--muted);
    font-size: .95rem;
    line-height: 1.8;
}
h2 {
    color: #4b3e41 !important;
    font-size: clamp(1.3rem, 5.6vw, 1.8rem) !important;
    line-height: 1.4 !important;
    margin-top: 2rem !important;
}
h3 {color: #4b3e41 !important;}
label, [data-testid="stWidgetLabel"] {color: #514548 !important;}
div.stButton > button {
    width: 100%;
    min-height: 3.15rem;
    border: 1px solid var(--rose) !important;
    border-radius: 999px;
    background: var(--rose) !important;
    color: white !important;
    font-weight: 700;
    box-shadow: 0 7px 18px rgba(135, 81, 92, .18);
}
div.stButton > button:hover {
    background: var(--rose-dark) !important;
    border-color: var(--rose-dark) !important;
}
div.stDownloadButton > button {
    border-color: var(--rose) !important;
    border-radius: 999px;
    color: var(--rose-dark) !important;
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
[data-testid="stAlert"] {border-radius: 16px;}
hr {border-color: var(--line) !important;}
.stCaption, [data-testid="stCaptionContainer"] {color: var(--muted) !important;}
@media (max-width: 640px) {
    .block-container {padding-left: 1rem; padding-right: 1rem;}
    .hero {padding: 1.55rem 1rem 1.3rem; border-radius: 20px;}
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<section class="hero">
  <div class="hero-mark"></div>
  <p class="hero-kicker">HAIR STYLE CONSULTATION</p>
  <h1>美容師さんお願いシート</h1>
  <p>似合いそうな髪型を試して、伝えたいイメージを<br>美容師さんに見せられる一枚に。</p>
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
    import japanize_matplotlib

    font_dir = Path(japanize_matplotlib.__file__).resolve().parent / "fonts"
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
    draw.line((350, 108, 1210, 108), fill="#9AA6B4", width=2)

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


uploaded = st.file_uploader("1. 顔写真を1枚アップロード", type=["jpg", "jpeg", "png"])
st.caption("正面に近く、顔と髪全体が明るく写った写真がおすすめです。写真はアプリ内に保存しません。")

if uploaded:
    try:
        original_image, image_buffer = normalized_image_bytes(uploaded)
        st.image(original_image, caption="アップロードした写真", use_container_width=True)
    except Exception:
        st.error("写真を読み込めませんでした。別のJPG・JPEG・PNG画像をお試しください。")
        st.stop()

    st.subheader("2. 希望を選択")
    mood = st.selectbox("なりたい雰囲気", ["おまかせ", "かわいい", "きれい", "かっこいい", "ナチュラル"])
    length = st.selectbox("髪の長さ", ["おまかせ", "ショート", "ボブ", "ミディアム", "ロング"])
    bangs = st.selectbox("前髪", ["おまかせ", "あり", "なし"])
    color = st.selectbox("髪色", ["おまかせ", "黒", "ブラウン", "ベージュ", "ピンク", "ブルー", "その他"])
    custom_color = st.text_input("希望する髪色を入力", placeholder="例：ブルーグレージュ") if color == "その他" else ""
    tone = st.slider("明るさ", 1, 15, 8, help="1が暗く、15が明るい目安です。")

    choices = {"雰囲気": mood, "長さ": length, "前髪": bangs, "髪色": custom_color or color, "明るさ": f"{tone}トーン"}
    consent = st.checkbox("写真が提案・画像生成のためOpenAI APIへ送信されることに同意します")

    if st.button("おすすめを3案つくる", type="primary", disabled=not consent):
        with st.spinner("似合いそうなスタイルを考えています…"):
            try:
                st.session_state.styles = propose_styles(get_client(), image_buffer, choices)
                st.session_state.pop("after_image", None)
                st.session_state.pop("style_sheet_png", None)
                st.session_state.pop("style_sheet_pdf", None)
            except Exception as exc:
                st.error(f"提案を作成できませんでした。もう一度お試しください。\n\n詳細: {exc}")

    if "styles" in st.session_state:
        st.subheader("3. 気になる案を選択")
        labels = []
        for index, style in enumerate(st.session_state.styles, 1):
            label = f"案{index}｜{style['title']}"
            labels.append(label)
            with st.container(border=True):
                st.markdown(f"**{label}**")
                st.write(f"髪型：{style['haircut']}")
                st.write(f"前髪：{style['bangs']}")
                st.write(f"カラー：{style['tone']}・{style['color']}")
                st.caption(style["reason"])

        selected_label = st.radio("生成する案", labels, label_visibility="collapsed")
        selected_index = labels.index(selected_label)
        selected_style = st.session_state.styles[selected_index]

        if st.button("この髪型にしてみる", type="primary"):
            with st.spinner("完成イメージを生成しています。しばらくお待ちください…"):
                try:
                    st.session_state.after_image = edit_hairstyle(get_client(), image_buffer, selected_style)
                    st.session_state.selected_style = selected_style
                    st.session_state.pop("style_sheet_png", None)
                    st.session_state.pop("style_sheet_pdf", None)
                except Exception as exc:
                    st.error(f"画像を生成できませんでした。もう一度お試しください。\n\n詳細: {exc}")

    if "after_image" in st.session_state:
        st.subheader("4. Before / After")
        left, right = st.columns(2)
        with left:
            st.image(original_image, caption="Before", use_container_width=True)
        with right:
            st.image(st.session_state.after_image, caption="After", use_container_width=True)
        st.download_button("完成画像を保存", st.session_state.after_image, "hair-style-after.jpg", "image/jpeg", use_container_width=True)

        st.subheader("5. 美容師さん向けオーダー文")
        st.text_area("このまま美容師さんに見せられます", st.session_state.selected_style["order"], height=160)

        st.subheader("6. 美容師向けスタイルシート")
        st.caption("正面・耳かけ・耳まわり・後ろ姿とオーダー内容を1枚にまとめます。追加の画像生成料金がかかります。")
        if st.button("美容師向けスタイルシートを作る", type="primary"):
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
                    st.error(f"スタイルシートを作成できませんでした。もう一度お試しください。\n\n詳細: {exc}")

        if "style_sheet_png" in st.session_state:
            st.image(st.session_state.style_sheet_png, caption="美容師向けスタイルシート", use_container_width=True)
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
else:
    st.info("最初に顔写真をアップロードしてください。")

st.divider()
st.caption("生成画像は参考イメージです。髪質や現在の髪の状態により、実際の仕上がりとは異なる場合があります。")
