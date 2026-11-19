"""Build the interactive benchmark deck: reads case data + PNGs, emits HTML."""

import base64
import json
import pathlib

EX = pathlib.Path(__file__).parent


def b64(p):
    return base64.b64encode((EX / p).read_bytes()).decode()


data = {
    "h1": json.load(open(EX / "case_data.json"))["h1"],
    "h2": json.load(open(EX / "case_h2_data.json")),
    "h2f": json.load(open(EX / "case_h2_final.json")),
    "helios": json.load(open(EX / "case_data.json"))["helios"],
    "conv": json.load(open(EX / "case_convergence.json")),
    "h1x": json.load(open(EX / "case_h1_extra.json")),
    "bend": json.load(open(EX / "case_bend_refine.json")),
}

imgs = {
    "h1": b64("case_h1.png"),
    "race": b64("case_racetrack_opt.png"),
    "jx_before": b64("case_junction_before.png"),
    "jx_fixed": b64("case_junction_fixed.png"),
}

template = (EX / "deck_template.html").read_text(encoding="utf-8")
html = template.replace("%%DATA%%", json.dumps(data))
for k, v in imgs.items():
    html = html.replace(f"%%IMG_{k.upper()}%%", v)
out = EX / "iontrap_claw_benchmark_deck.html"
out.write_text(html, encoding="utf-8")
print("written", out, out.stat().st_size, "bytes")
