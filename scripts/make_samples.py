"""Generate fake sample documents for OCR tests and the demo (task C5).

Run from the repo root:  uv run --with pillow python scripts/make_samples.py
Writes content/samples/*.png. Every image is stamped "SAMPLE — NOT A REAL REPORT";
all names, clinics and numbers are invented. Output is deterministic.

Later tasks depend on exact strings: lab_report_cbc.png has "Haemoglobin 10.2 g/dL" with
reference "12.0–15.0", dated 12/08/2026; rx_allopathic.png has "Tab Metformin 500 mg BD x 30 days"
and "Tab Amlodipine 5 mg OD".
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "content" / "samples"
W, H = 1240, 1754  # A4 at 150 dpi
STAMP = "SAMPLE — NOT A REAL REPORT"
INK = (15, 15, 15)
RED = (200, 20, 20)
GREY = (90, 90, 90)

FONT_DIRS = [Path("/System/Library/Fonts/Supplemental"), Path("/System/Library/Fonts"), Path("/Library/Fonts")]
REGULAR = ["Arial.ttf", "Helvetica.ttc", "Verdana.ttf"]
BOLD = ["Arial Bold.ttf", "Verdana Bold.ttf", "Helvetica.ttc"]
HAND = ["Bradley Hand Bold.ttf", "Noteworthy.ttc", "MarkerFelt.ttc", "Chalkboard.ttc"]


def font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in candidates:
        for d in FONT_DIRS:
            if (d / name).exists():
                return ImageFont.truetype(str(d / name), size)
    return ImageFont.load_default(size=size)


class Page:
    def __init__(self, bg: tuple[int, int, int] = (255, 255, 255)) -> None:
        self.img = Image.new("RGB", (W, H), bg)
        self.d = ImageDraw.Draw(self.img)
        self.y = 60
        self.stamp_banner()

    def stamp_banner(self) -> None:
        f = font(BOLD, 40)
        box = self.d.textbbox((0, 0), STAMP, font=f)
        tw = box[2] - box[0]
        x = (W - tw) // 2
        self.d.rectangle((x - 24, self.y - 12, x + tw + 24, self.y + 58), outline=RED, width=5)
        self.d.text((x, self.y), STAMP, font=f, fill=RED)
        self.y += 100

    def text(self, s: str, size: int = 32, bold: bool = False, x: int = 80, fill=INK, gap: int = 14) -> None:
        f = font(BOLD if bold else REGULAR, size)
        self.d.text((x, self.y), s, font=f, fill=fill)
        self.y += size + gap

    def center(self, s: str, size: int, bold: bool = True, fill=INK) -> None:
        f = font(BOLD if bold else REGULAR, size)
        box = self.d.textbbox((0, 0), s, font=f)
        self.d.text(((W - (box[2] - box[0])) // 2, self.y), s, font=f, fill=fill)
        self.y += size + 16

    def rule(self, width: int = 3) -> None:
        self.d.line((80, self.y, W - 80, self.y), fill=INK, width=width)
        self.y += 24

    def row(self, cells: list[str], xs: list[int], size: int = 32, bold: bool = False) -> None:
        f = font(BOLD if bold else REGULAR, size)
        for cell, x in zip(cells, xs, strict=True):
            self.d.text((x, self.y), cell, font=f, fill=INK)
        self.y += size + 22

    def space(self, px: int = 24) -> None:
        self.y += px

    def footer(self) -> None:
        f = font(BOLD, 28)
        s = f"{STAMP} · fictional data for software testing"
        box = self.d.textbbox((0, 0), s, font=f)
        self.d.text(((W - (box[2] - box[0])) // 2, H - 90), s, font=f, fill=RED)

    def save(self, name: str) -> Image.Image:
        self.footer()
        self.img.save(OUT / name)
        return self.img


def lab_header(p: Page, lab: str, address: str) -> None:
    p.center(lab, 48)
    p.center(address, 26, bold=False, fill=GREY)
    p.space(10)
    p.rule()


def patient_block(
    p: Page, name: str, age_sex: str, date: str, ref: str | None, extra: str = "Sample ID: SMP-0000"
) -> None:
    p.row([f"Patient: {name}", f"Age/Sex: {age_sex}"], [80, 760])
    p.row([f"Date: {date}", extra], [80, 760])
    if ref:
        p.row([f"Referred by: {ref}", ""], [80, 760])
    p.rule(2)


LAB_XS = [80, 520, 720, 920]


def lab_report_cbc() -> Image.Image:
    p = Page()
    lab_header(p, "Sunrise Diagnostics (Sample Lab)", "12 Example Road, Demo Nagar · Tel 00000 00000")
    patient_block(p, "Kamla Devi", "62 / F", "12/08/2026", "Dr. A. Kulkarni")
    p.center("COMPLETE BLOOD COUNT (CBC)", 38)
    p.space(6)
    p.row(["Test", "Result", "Unit", "Reference"], LAB_XS, bold=True)
    p.rule(2)
    for cells in [
        ["Haemoglobin", "10.2", "g/dL", "12.0–15.0"],
        ["Total WBC count", "7.8", "x10^3/uL", "4.0–11.0"],
        ["Platelet count", "210", "x10^3/uL", "150–410"],
        ["RBC count", "4.1", "x10^6/uL", "3.8–4.8"],
        ["PCV (Haematocrit)", "32.5", "%", "36.0–46.0"],
        ["MCV", "79", "fL", "83–101"],
    ]:
        p.row(cells, LAB_XS)
    p.rule(2)
    p.space(20)
    p.text("Method: automated cell counter.", size=28, fill=GREY)
    p.text("Reported by: Lab Technician (Sample)", size=28, fill=GREY)
    return p.save("lab_report_cbc.png")


def lab_report_diabetes() -> None:
    p = Page()
    lab_header(p, "Sunrise Diagnostics (Sample Lab)", "12 Example Road, Demo Nagar · Tel 00000 00000")
    patient_block(p, "Rahul Verma", "45 / M", "05/07/2026", "Self", "Sample ID: SMP-0001")
    p.center("DIABETES PROFILE", 38)
    p.space(6)
    p.row(["Test", "Result", "Unit", "Reference"], LAB_XS, bold=True)
    p.rule(2)
    for cells in [
        ["Fasting blood sugar", "142", "mg/dL", "70–100"],
        ["Post-prandial sugar", "198", "mg/dL", "70–140"],
        ["HbA1c", "7.4", "%", "4.0–5.6"],
    ]:
        p.row(cells, LAB_XS)
    p.rule(2)
    p.space(20)
    p.text("Sample: venous blood, fasting 10 hours.", size=28, fill=GREY)
    p.save("lab_report_diabetes.png")


def clinic_header(p: Page, doctor: str, quals: str, clinic: str) -> None:
    p.text(doctor, size=46, bold=True)
    p.text(quals, size=28, fill=GREY)
    p.text(clinic, size=28, fill=GREY, gap=20)
    p.rule()


def rx_allopathic() -> Image.Image:
    p = Page()
    clinic_header(p, "Dr. A. Kulkarni", "MBBS, MD (Medicine) · Reg. No. SAMPLE-0000", "Demo Care Clinic, 4 Test Lane")
    patient_block(p, "Kamla Devi", "62 / F", "12/08/2026", None, "OPD No: SMP-0002")
    p.text("Diagnosis: Type 2 diabetes mellitus, Hypertension", size=32)
    p.space(10)
    p.text("Rx", size=56, bold=True)
    p.text("Tab Metformin 500 mg BD x 30 days", size=38, x=120, gap=26)
    p.text("Tab Amlodipine 5 mg OD", size=38, x=120, gap=26)
    p.space(20)
    p.text("Advice: low-salt diet, walk 30 minutes daily.", size=30)
    p.text("Review after 1 month with FBS report.", size=30)
    p.space(120)
    p.text("Signature: ______________", size=30, x=760)
    return p.save("rx_allopathic.png")


def rx_ayurveda() -> None:
    p = Page()
    clinic_header(
        p, "Vd. S. Joshi", "BAMS, MD (Ayurveda) · Reg. No. SAMPLE-0001", "Demo Ayurveda Chikitsalaya, 9 Test Marg"
    )
    patient_block(p, "Kamla Devi", "62 / F", "20/06/2026", None, "OPD No: SMP-0003")
    p.text("Complaint: Knee pain, morning stiffness", size=32)
    p.space(10)
    p.text("Rx", size=56, bold=True)
    p.text("Yograj Guggulu 2 tab BD after food", size=38, x=120, gap=26)
    p.text("Dashmool Kwath 20 ml BD", size=38, x=120, gap=26)
    p.space(20)
    p.text("Pathya: warm water, avoid cold and heavy food.", size=30)
    p.text("Review after 15 days.", size=30)
    p.space(120)
    p.text("Signature: ______________", size=30, x=760)
    p.save("rx_ayurveda.png")


def discharge_summary() -> None:
    p = Page()
    lab_header(p, "Demo City Hospital (Sample)", "Department of General Medicine · 1 Example Avenue")
    p.center("DISCHARGE SUMMARY", 40)
    p.space(4)
    patient_block(p, "Rahul Verma", "45 / M", "03/03/2026", "Dr. P. Menon", "IP No: SMP-0004")
    for label, value in [
        ("Date of admission", "28/02/2026"),
        ("Date of discharge", "03/03/2026"),
        ("Final diagnosis", "Community-acquired pneumonia"),
        ("Known history", "Type 2 diabetes mellitus"),
    ]:
        p.row([f"{label}:", value], [80, 480])
    p.space(6)
    p.text("Course in hospital:", size=32, bold=True)
    p.text("Admitted with fever and cough for 5 days. Treated with IV", size=30)
    p.text("antibiotics and oxygen. Improved, afebrile for 48 hours.", size=30, gap=24)
    p.text("Medicines on discharge:", size=32, bold=True)
    p.text("Tab Amoxicillin 500 mg TDS x 5 days", size=34, x=120)
    p.text("Tab Paracetamol 650 mg SOS", size=34, x=120)
    p.text("Tab Metformin 500 mg BD", size=34, x=120, gap=24)
    p.text("Follow-up: Medicine OPD after 7 days.", size=30)
    p.save("discharge_summary.png")


def handwritten_style() -> None:
    img = Image.new("RGB", (W, H), (252, 249, 238))
    d = ImageDraw.Draw(img)
    for y in range(300, H - 160, 70):  # ruled notepad lines
        d.line((60, y, W - 60, y), fill=(190, 205, 230), width=2)
    stamp_font = font(BOLD, 40)
    box = d.textbbox((0, 0), STAMP, font=stamp_font)
    x = (W - (box[2] - box[0])) // 2
    d.rectangle((x - 24, 48, x + box[2] - box[0] + 24, 118), outline=RED, width=5)
    d.text((x, 60), STAMP, font=stamp_font, fill=RED)
    ink = (20, 40, 120)
    lines = [
        (48, "Dr. R. Sen  (sample clinic)"),
        (40, "Kamla Devi  62 F       2/9/2026"),
        (40, "c/o acidity, knee pain"),
        (60, "Rx"),
        (44, "Tab Pantoprazole 40 mg OD"),
        (44, "   before breakfast x 14 days"),
        (44, "Tab Paracetamol 650 mg SOS"),
        (40, "Review after 2 weeks"),
    ]
    y = 225
    for size, s in lines:
        d.text((100, y), s, font=font(HAND, size), fill=ink)
        y += 70 if size < 50 else 90
    f = font(BOLD, 28)
    s = f"{STAMP} · fictional data for software testing"
    box = d.textbbox((0, 0), s, font=f)
    d.text(((W - (box[2] - box[0])) // 2, H - 90), s, font=f, fill=RED)
    img.save(OUT / "handwritten_style.png")


def photographed(img: Image.Image, name: str, angle: float) -> None:
    """Fake a phone photo: page on a darker desk, slight rotation, blur, uneven light."""
    page = img.resize((W * 3 // 4, H * 3 // 4), Image.Resampling.LANCZOS)
    page = page.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(0, 0, 0))
    mask = Image.new("L", (W * 3 // 4, H * 3 // 4), 255).rotate(angle, expand=True, fillcolor=0)
    canvas = Image.new("RGB", (page.width + 160, page.height + 160), (96, 78, 60))
    canvas.paste(page, (80, 80), mask)
    # Shadow falling from the left: dark at the left edge fading to none by mid-page.
    grad = Image.linear_gradient("L").rotate(90, expand=True).resize(canvas.size)
    shade = grad.point(lambda v: int(max(0, 110 - v)))
    canvas = Image.composite(Image.new("RGB", canvas.size, (0, 0, 0)), canvas, shade)
    canvas = canvas.filter(ImageFilter.GaussianBlur(1.1))
    canvas.save(OUT / name)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cbc = lab_report_cbc()
    lab_report_diabetes()
    rx = rx_allopathic()
    rx_ayurveda()
    discharge_summary()
    handwritten_style()
    photographed(cbc, "lab_report_cbc_photo.png", angle=3.0)
    photographed(rx, "rx_allopathic_photo.png", angle=-4.0)
    for p in sorted(OUT.glob("*.png")):
        with Image.open(p) as im:
            print(f"{p.name}: {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    main()
