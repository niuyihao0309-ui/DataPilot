# 文件格式转换的工具模块
from app.utils.logger_utils import logger
from pathlib import Path
import markdown
# ⚠️ win32com / pythoncom 来自 pywin32，只有 Windows 才有。
#    绝不能在模块顶层 import：Linux 容器里一加载本模块就抛 ModuleNotFoundError，
#    会把整个 backend（main.py → ws_routes → main_agent → pdf_tools）连带带崩。
#    所以改成「用到时再 import」，见下面函数体内的延迟导入。
# import win32com.client
# import pythoncom

def convert_md_to_pdf_via_word(md_abs_path: Path, pdf_abs_path: Path) -> str:
    """
    使用 Microsoft Word COM 接口将 Markdown 转换为 PDF。
    依赖：pywin32, markdown
    """
    # 延迟导入：非 Windows 环境（如 Linux 容器）在这里直接友好返回，
    # 不会影响本模块被其它代码正常 import。
    try:
        import win32com.client
        import pythoncom
    except ImportError:
        return "当前运行环境不支持 Word 转 PDF（缺少 pywin32，该功能仅 Windows 可用）"

    temp_html_path = md_abs_path.with_suffix('.temp.html')
    word_app = None

    try:
        # 1. MD 转 HTML
        with open(md_abs_path, 'r', encoding='utf-8') as f:
            md_content = f.read()

        html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code'])
        html_content = f"""
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: "Microsoft YaHei", "SimHei", sans-serif; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid black; padding: 8px; }}
                pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 4px; }}
                code {{ font-family: "Consolas", "Monaco", monospace; }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """

        with open(temp_html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

        # 2. 调用 Word COM
        pythoncom.CoInitialize()
        word_app = win32com.client.Dispatch('Word.Application')
        word_app.Visible = False
        word_app.DisplayAlerts = False

        doc = word_app.Documents.Open(str(temp_html_path.resolve()))
        doc.SaveAs(str(pdf_abs_path.resolve()), FileFormat=17)  # wdFormatPDF = 17
        doc.Close(SaveChanges=0)

        if pdf_abs_path.exists():
            return f"成功转换: {pdf_abs_path} (Word引擎)"
        else:
            return f"转换完成但未生成文件: {pdf_abs_path}"

    except ImportError:
        return "缺少依赖库，请安装: pip install pywin32 markdown"
    except Exception as e:
        logger.error(f"Word转换PDF失败: {e}", exc_info=True)
        return f"转换失败: {str(e)}"
    finally:
        # 3. 资源清理
        if word_app:
            try:
                word_app.Quit()
            except Exception as e:
                logger.warning(f"关闭Word应用时出错: {e}")

        if temp_html_path.exists():
            try:
                temp_html_path.unlink()
            except Exception as e:
                logger.warning(f"删除临时HTML文件时出错: {e}")

        try:
            pythoncom.CoUninitialize()
        except Exception as e:
            logger.warning(f"释放COM初始化时出错: {e}")