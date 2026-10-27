"""一次性修正：把改动文件里的连续替换字符（U+FFFD+）还原成正确汉字。用完即删。"""
import io
import re

R = "\ufffd+"


def fix(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for a, b in pairs:
        s, n = re.subn(a, b, s)
        if n == 0:
            print("MISS", path, a)
    io.open(path, "w", encoding="utf-8", newline="\n").write(s)
    print("fixed", path)


fix("PROJECT.md", [
    ("画布" + R + " 309px", "画布从 309px"),
    ("触发器/" + R + "项/注释", "触发器/选项/注释"),
])
fix("backend/app/static/app.js", [
    ("// 游" + R + "：上传", "// 游客：上传"),
    ("显示超出" + R + "少）", "显示超出多少）"),
])
fix("docker-compose.yml", [("反代配" + R + "加上", "反代配置加上")])
fix("tests/local_test.py", [("XFF 含非" + R + "段时跳过", "XFF 含非法段时跳过")])
