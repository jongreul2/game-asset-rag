"""캡처한 PNG 프레임 폴더를 GIF로 만든다.

사용: python tools/make_gif.py artifacts/frames/gate docs/images/gate-demo.gif --fps 12 --width 960
"""
import argparse
import pathlib

from PIL import Image


def paste_inset(image: Image.Image, inset_path: pathlib.Path, scale: float, pos: str = "br") -> None:
    """같은 번호의 다른 카메라 프레임을 아래쪽 모서리 작은 창(흰 테두리)으로 겹친다."""
    if not inset_path.exists():
        return
    inset = Image.open(inset_path).convert("RGB")
    width = round(image.width * scale)
    height = round(inset.height * width / inset.width)
    inset = inset.resize((width, height), Image.LANCZOS)
    margin, border = 12, 3
    x = image.width - width - margin if pos == "br" else margin
    y = image.height - height - margin
    image.paste((235, 238, 244), (x - border, y - border, x + width + border, y + height + border))
    image.paste(inset, (x, y))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frames", type=pathlib.Path)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--fps", type=float, default=12)
    parser.add_argument("--width", type=int, default=960)
    parser.add_argument("--colors", type=int, default=128)
    parser.add_argument("--hold-last", type=float, default=1.5, help="마지막 프레임 정지 시간(초)")
    parser.add_argument("--inset", type=pathlib.Path, help="오른쪽 아래 작은 창에 겹칠 프레임 폴더(같은 번호)")
    parser.add_argument("--inset-scale", type=float, default=0.36, help="작은 창 너비 / 전체 너비")
    parser.add_argument("--inset-pos", choices=["br", "bl"], default="br", help="작은 창 위치(오른쪽/왼쪽 아래)")
    args = parser.parse_args()

    paths = sorted(args.frames.glob("*.png"))
    if not paths:
        raise SystemExit(f"프레임 없음: {args.frames}")

    frames = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        if image.width != args.width:
            height = round(image.height * args.width / image.width)
            image = image.resize((args.width, height), Image.LANCZOS)
        if args.inset:
            paste_inset(image, args.inset / path.name, args.inset_scale, args.inset_pos)
        frames.append(image)

    # 팔레트 하나를 모든 프레임이 공유하면 프레임 간 색이 튀지 않는다. 첫 프레임만 보면 나중에 나오는 색
    # (배지의 초록·주황 등)이 빠지므로, 고르게 뽑은 프레임 16장을 이어 붙인 그림에서 팔레트를 만든다.
    picks = [frames[round(i * (len(frames) - 1) / 15)] for i in range(16)]
    sheet = Image.new("RGB", (picks[0].width * 4, picks[0].height * 4))
    for i, pick in enumerate(picks):
        sheet.paste(pick, ((i % 4) * pick.width, (i // 4) * pick.height))
    palette = sheet.quantize(colors=args.colors, method=Image.Quantize.MAXCOVERAGE)  # 면적이 작은 강조색도 살린다
    quantized = [frame.quantize(palette=palette, dither=Image.Dither.NONE) for frame in frames]

    frame_ms = round(1000 / args.fps)
    durations = [frame_ms] * len(quantized)
    durations[-1] = round(args.hold_last * 1000)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    quantized[0].save(
        args.output,
        save_all=True,
        append_images=quantized[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=1,
    )
    size_kb = args.output.stat().st_size / 1024
    print(f"{args.output}: {len(quantized)} frames, {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
