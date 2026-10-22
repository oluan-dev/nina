"""O rosto da Nina flutuando no canto da tela — só o rosto, sem janela nem fundo.

Sobe junto com a Nina (`python -m conversa`) ou sozinho, pelo comando abaixo.

A arte (`arte/rosto.png`, holograma ciano sobre azul-noite) não tem canal de
transparência. Aqui o fundo vira transparente pela própria luz: o que é escuro
como o fundo some, o meio-tom do rosto fica translúcido e os traços acesos ficam
inteiros — por isso parece holograma em cima do que estiver atrás. A janela é
"em camada" do Windows (UpdateLayeredWindow, alfa por pixel): onde não há
rosto, o clique passa direto para o que está embaixo.

A boca é a mesma do `rosto.html`: `nina/boca.py` escreve em `diario/boca.json` a
forma do som que acabou de tocar, e aqui só se troca o quadro.

    python -m nina.rosto_flutuante              mostra (arrastar move; botão direito fecha)
    python -m nina.rosto_flutuante --previa F   grava F.png com o rosto sobre claro/escuro
"""
from __future__ import annotations

import ctypes
import json
import sys
import threading
from ctypes import wintypes
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RAIZ = Path(__file__).resolve().parent.parent
ARTE = Path(__file__).resolve().parent / "arte"
BOCA = RAIZ / "diario" / "boca.json"
POSICAO = RAIZ / "memoria" / "rosto-posicao.txt"

ALTURA = 230                 # px na tela (a arte tem 400x669)
MARGEM = 16                  # do canto da área de trabalho
FORMAS = ("M", "S", "AH", "E", "O")
CAIXA_DA_BOCA = (104, 368, 200, 140)   # x, y, l, a em arte/rosto.png (ver rosto.html)
RAIO = 14                    # px dos cantos arredondados


def _mascara_da_boca(l: int, a: int) -> Image.Image:
    """A borda do recorte da boca some (a mesma máscara radial do rosto.html)."""
    m = Image.new("L", (l, a), 0)
    ImageDraw.Draw(m).ellipse((l * 0.14, a * 0.15, l * 0.86, a * 0.85), fill=255)
    return m.filter(ImageFilter.GaussianBlur(min(l, a) * 0.12))


def quadro(forma: str, altura: int = ALTURA) -> np.ndarray:
    """O rosto com a boca `forma`, em BGRA pré-multiplicado (o que o Windows quer)."""
    rosto = Image.open(ARTE / "rosto.png").convert("RGB")
    x, y, l, a = CAIXA_DA_BOCA
    boca = Image.open(ARTE / f"boca-{forma}.png").convert("RGB").resize((l, a))
    rosto.paste(boca, (x, y), _mascara_da_boca(l, a))
    largura = round(rosto.width * altura / rosto.height)
    rosto = rosto.resize((largura, altura), Image.LANCZOS)
    rgb = np.asarray(rosto).astype(np.float32)
    # A imagem inteira, com o fundo dela, sólida. Recortar o fundo foi o
    # primeiro jeito e ficou esquisito. Só os cantos arredondam, para não
    # parecer janela.
    canto = Image.new("L", (largura, altura), 0)
    ImageDraw.Draw(canto).rounded_rectangle((0, 0, largura - 1, altura - 1),
                                            radius=RAIO, fill=255)
    alfa = np.asarray(canto).astype(np.float32) / 255
    bgra = np.empty((altura, largura, 4), np.uint8)
    bgra[..., :3] = (rgb[..., ::-1] * alfa[..., None]).clip(0, 255)
    bgra[..., 3] = (alfa * 255).astype(np.uint8)
    return bgra


def previa(caminho: str) -> None:
    """O rosto sobre fundo claro e escuro, para conferir antes de pôr na tela."""
    q = quadro("AH")
    a = q[..., 3:4].astype(np.float32) / 255
    cor = q[..., 2::-1].astype(np.float32)
    lados = []
    for fundo in ((235, 235, 235), (40, 44, 52)):
        base = np.full(cor.shape, fundo, np.float32)
        lados.append((cor + base * (1 - a)).clip(0, 255).astype(np.uint8))
    Image.fromarray(np.concatenate(lados, axis=1)).save(caminho)


# ------------------------------------------------------------ a janela

user32, gdi32, kernel32 = ctypes.windll.user32, ctypes.windll.gdi32, ctypes.windll.kernel32
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                             wintypes.LPARAM)
user32.DefWindowProcW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.DefWindowProcW.restype = LRESULT
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = (
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.HMENU,
    wintypes.HINSTANCE, wintypes.LPVOID)
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.SelectObject.argtypes = (wintypes.HDC, wintypes.HGDIOBJ)
gdi32.DeleteObject.argtypes = (wintypes.HGDIOBJ,)

WS_POPUP = 0x80000000
WS_EX_LAYERED, WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x80000, 0x8, 0x80, 0x8000000
WM_NCHITTEST, WM_NCRBUTTONUP, WM_EXITSIZEMOVE, WM_TIMER, WM_DESTROY = 0x84, 0xA5, 0x232, 0x113, 0x2
HTCAPTION, ULW_ALPHA = 2, 2


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class Rosto:
    def __init__(self) -> None:
        self.quadros = {f: quadro(f) for f in FORMAS}
        self.alt, self.larg = self.quadros["M"].shape[:2]
        self.forma = ""
        self._proc = WNDPROC(self._wndproc)       # guardado: o GC não pode levar

    def _canto(self) -> tuple[int, int]:
        try:
            x, y = (int(v) for v in POSICAO.read_text().split(","))
            return x, y
        except (OSError, ValueError):
            # Canto inferior esquerdo da área de trabalho.
            area = wintypes.RECT()
            user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0)   # SPI_GETWORKAREA
            return area.left + MARGEM, area.bottom - self.alt - MARGEM

    def _mostrar(self, forma: str) -> None:
        if forma == self.forma or forma not in self.quadros:
            return
        self.forma = forma
        tela = user32.GetDC(None)
        dc = gdi32.CreateCompatibleDC(tela)
        cab = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), self.larg, -self.alt, 1, 32, 0,
                               0, 0, 0, 0, 0)
        bits = ctypes.c_void_p()
        bmp = gdi32.CreateDIBSection(dc, ctypes.byref(cab), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, self.quadros[forma].tobytes(), self.larg * self.alt * 4)
        antigo = gdi32.SelectObject(dc, bmp)
        tamanho, origem = wintypes.SIZE(self.larg, self.alt), wintypes.POINT(0, 0)
        mistura = BLENDFUNCTION(0, 0, 255, 1)              # AC_SRC_OVER, AC_SRC_ALPHA
        user32.UpdateLayeredWindow(self.janela, tela, None, ctypes.byref(tamanho), dc,
                                   ctypes.byref(origem), 0, ctypes.byref(mistura), ULW_ALPHA)
        gdi32.SelectObject(dc, antigo)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(dc)
        user32.ReleaseDC(None, tela)

    def _wndproc(self, janela, msg, wp, lp):
        if msg == WM_NCHITTEST:
            return HTCAPTION                         # arrastar em qualquer ponto do rosto
        if msg == WM_EXITSIZEMOVE:
            r = wintypes.RECT()
            user32.GetWindowRect(janela, ctypes.byref(r))
            try:
                POSICAO.write_text(f"{r.left},{r.top}")
            except OSError:
                pass
            return 0
        if msg == WM_NCRBUTTONUP:
            user32.DestroyWindow(janela)
            return 0
        if msg == WM_TIMER:
            try:
                self._mostrar(json.loads(BOCA.read_text(encoding="utf8")).get("forma", "M"))
            except (OSError, ValueError):
                self._mostrar("M")
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(janela, msg, wp, lp)

    def rodar(self) -> None:
        """Cria a janela e fica no laço de mensagens (bloqueia; use num fio)."""
        self._trava = kernel32.CreateMutexW(None, False, "Local\\NinaRostoFlutuante")
        if kernel32.GetLastError() == 183:                 # ERROR_ALREADY_EXISTS
            return                                         # já tem um rosto na tela
        instancia = kernel32.GetModuleHandleW(None)
        classe = WNDCLASSW(lpfnWndProc=self._proc, hInstance=instancia,
                           lpszClassName="NinaRostoFlutuante",
                           hCursor=user32.LoadCursorW(None, 32649))   # mãozinha: dá pra arrastar
        user32.RegisterClassW(ctypes.byref(classe))
        x, y = self._canto()
        self.janela = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            "NinaRostoFlutuante", "Nina", WS_POPUP, x, y, self.larg, self.alt,
            None, None, instancia, None)
        self._mostrar("M")
        user32.ShowWindow(self.janela, 4)                  # SW_SHOWNOACTIVATE
        user32.SetTimer(self.janela, 1, 33, None)          # o mesmo passo do boca.py
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


def ligar() -> threading.Thread:
    """Sobe o rosto num fio à parte: vive e morre junto com a Nina."""
    fio = threading.Thread(target=lambda: Rosto().rodar(), daemon=True)
    fio.start()
    return fio


if __name__ == "__main__":
    if "--previa" in sys.argv:
        previa(sys.argv[sys.argv.index("--previa") + 1])
    else:
        Rosto().rodar()
