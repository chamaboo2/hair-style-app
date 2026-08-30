import base64
import io
import json

import streamlit as st
from openai import OpenAI
from PIL import Image
from pydantic import BaseModel, Field


st.set_page_config(page_title="AIヘアスタイル", page_icon="✂️", layout="centered")

st.markdown("""
<style>
.block-container {max-width: 720px; padding-top: 1.2rem; padding-bottom: 3rem;}
div.stButton > button {width: 100%; border-radius: 12px; min-height: 3rem; font-weight: 700;}
[data-testid="stFileUploader"] {border-radius: 14px;}
</style>
""", unsafe_allow_html=True)

st.title("✂️ AIヘアスタイル")
st.caption("顔写真から似合いそうな髪型を提案し、完成イメージを作ります。")


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
else:
    st.info("最初に顔写真をアップロードしてください。")

st.divider()
st.caption("生成画像は参考イメージです。髪質や現在の髪の状態により、実際の仕上がりとは異なる場合があります。")
