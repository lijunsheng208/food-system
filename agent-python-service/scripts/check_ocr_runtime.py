"""检查 PDF/DOCX 图片 OCR 的系统依赖，不触发模型下载。"""

import importlib.util
import shutil
import subprocess
import sys


# 检查可执行文件、语言包和推理依赖；模型是否可用仍需真实样本验收。
def main() -> int:
    errors = []
    for command in ("tesseract", "pdfinfo", "pdftoppm"):
        if shutil.which(command) is None:
            errors.append("缺少系统命令：" + command)
    if shutil.which("tesseract") is not None:
        try:
            result = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True, check=True, timeout=15)
            languages = set((result.stdout + result.stderr).split())
            for language in ("chi_sim", "eng"):
                if language not in languages:
                    errors.append("缺少 Tesseract 语言包：" + language)
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append("Tesseract 语言包检查失败：" + str(exc))
    for module in ("unstructured_inference", "unstructured_pytesseract", "onnxruntime", "PIL"):
        if importlib.util.find_spec(module) is None:
            errors.append("缺少 Python 模块：" + module)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("OCR 系统依赖检查通过；请继续运行真实 PDF/Word OCR 用例验证模型与识别结果。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
