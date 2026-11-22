from playwright.sync_api import sync_playwright
import json
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome",args=["--autoplay-policy=no-user-gesture-required"])
    page = browser.new_page()
    page.add_init_script("""window.playLog=[]; const start=AudioBufferSourceNode.prototype.start;AudioBufferSourceNode.prototype.start=function(...args){const b=this.buffer;if(b && this.context instanceof AudioContext){const x=b.getChannelData(0);let peak=0,ss=0;for(const s of x){peak=Math.max(peak,Math.abs(s));ss+=s*s}window.playLog.push({rate:b.sampleRate,frames:b.length,peak,rms:Math.sqrt(ss/x.length),state:this.context.state})}return start.apply(this,args)}""")
    page.goto("https://reactbits.dev/tools/sound-lab",wait_until="domcontentloaded",timeout=60000)
    page.wait_for_timeout(2500)
    import re
    for library in ["Interface","Video"]:
        page.get_by_role("button",name=re.compile("^"+library+r"\s*100")).evaluate("(b)=>b.click()")
        if library=="Video":
            print(page.locator("body").inner_text()[:1100],flush=True)
            first=page.get_by_role("button",name="Show",exact=True).locator("xpath=following::button[1]")
            print("selected",first.inner_text(),flush=True)
            first.evaluate("(b)=>b.click()")
            page.wait_for_timeout(1000)
        page.get_by_role("button",name="Play",exact=True).first.evaluate("(b)=>b.click()")
        page.wait_for_timeout(1200)
        print(library,page.evaluate("window.playLog"),flush=True)
