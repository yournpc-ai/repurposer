"""Original Repurposer research descriptions; every control is an integer."""
def knob(unit, default, low, high, description):
    return dict(type="integer", unit=unit, default=default, minimum=low, maximum=high, description=description)

def recipe(name, category, sound, use, avoid, suggested, mix, **controls):
    return dict(name=name, category=category, impression=sound, visual_action=use, avoid=avoid,
                suggested_duration_ms=suggested, mix=mix, version=1,
                parameters=dict(type="object", additionalProperties=False, properties=controls))

catalog = {
    "whoosh": recipe("掠入", "motion", "从窄到宽的一束气流，靠近时音色抬起，掠过后散去。",
                     "标题侧滑、产品卡飞入", "静止标题、写实风声", [300,650],
                     "峰值跟随最快运动，旁白齿音上先降低明亮度，再调片段电平。",
                     duration=knob("ms",560,150,1000,"改变气流展开时间；过短会失去运动过程。"),
                     pitch=knob("Hz",410,180,760,"移动气流共振与微弱滑音的中心；高端易与女声争位。"),
                     tone=knob("%",58,10,90,"提高高频气声带的中心和占比；密集旁白宜收暗。"),
                     travel=knob("%",66,0,100,"同时增加扫频跨度与左右移动幅度；单声道折叠时方位减弱。")),
    "impact": recipe("轻落", "accent", "短促触点后留下圆润的低音与稀疏反射。",
                     "Logo 或标题落定", "连续按钮、爆炸拟音", [180,500],
                     "已有鼓点时避开重复重拍，低音厚度须在小扬声器上复听。",
                     body=knob("Hz",115,55,180,"降低主体共振频率使落点低沉；最低端小扬声器可能听不清。"),
                     punch=knob("%",48,5,90,"缩短起音并增加短促高次振动；太大会盖住字头。"),
                     tail=knob("ms",370,120,650,"控制低音衰减及整个尾窗；过短减少重量。"),
                     space=knob("%",24,0,80,"提高左右早期反射的比例；紧密落点易拖糊。")),
    "click": recipe("圆点", "interface", "一粒短音，带温和的空腔共鸣。",
                    "按下按钮、卡片确认", "长转场、连续键盘写实录音", [65,65],
                    "重复点击保持低增益，检查密集操作时是否打断辅音。",
                    pitch=knob("Hz",830,380,1300,"调整短音的主体频率；高端重复播放易疲劳。"),
                    hardness=knob("%",55,5,90,"增加短促泛音并加快起音；极软状态对弱扬声器不够清晰。"))
}
