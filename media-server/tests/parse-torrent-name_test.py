import PTN

# 解析第一个文件
path1 = "/dav/302/156quark302/剧集/请回答1988(2015)/请回答1988.内嵌官方中字.S01E14.2160p.TVING.WEB-DL.AC3.HFR.H.265.mkv"
result1 = PTN.parse(path1)
print("解析结果1：", result1)

# 解析第二个文件
path2 = "/dav/302/156quark302/剧集/鹊刀门传奇（2023）全40集 内嵌简中字幕 4K+1080P/01.mp4"
result2 = PTN.parse(path2)
print("解析结果2：", result2)