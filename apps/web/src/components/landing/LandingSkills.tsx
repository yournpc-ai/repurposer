import { useRef, useState } from "react"
import { ArrowUp } from "lucide-react"
import { useMotionValueEvent, useScroll } from "motion/react"
import { useTranslation } from "react-i18next"
import { LANDING_GALLERY } from "./content"
import { useReducedMotion } from "./motion"
import { useLandingCreate } from "./useLandingCreate"

const FRAME_NUMBERS = [1, 2, 3, 4]
const LAST_SKILL = LANDING_GALLERY.length - 1
const HEADER_HEIGHT = 64

export function LandingSkills() {
  const { t } = useTranslation()
  const create = useLandingCreate()
  const reduce = useReducedMotion()
  const section = useRef<HTMLElement>(null)
  const stage = useRef<HTMLDivElement>(null)
  const [active, setActive] = useState(0)
  const { scrollYProgress } = useScroll({
    target: section,
    offset: [`start ${HEADER_HEIGHT}px`, "end end"],
  })

  useMotionValueEvent(scrollYProgress, "change", (progress) => {
    if (!reduce && section.current && stage.current && section.current.offsetHeight > stage.current.offsetHeight) {
      setActive(Math.round(progress * LAST_SKILL))
    }
  })

  function selectSkill(index: number) {
    setActive(index)
    if (reduce || !section.current || !stage.current) return

    const travel = section.current.offsetHeight - stage.current.offsetHeight
    if (travel > 0) {
      const start = window.scrollY + section.current.getBoundingClientRect().top - HEADER_HEIGHT
      window.scrollTo({ top: start + travel * index / LAST_SKILL, behavior: "instant" })
    }
  }

  return (
    <section ref={section} id="skills" aria-labelledby="landing-skills-title" className="landing-skills">
      <div ref={stage} className="landing-skills-stage">
        <div className="landing-skills-heading text-center">
          <h2 id="landing-skills-title" className="font-hero leading-[1.16]">
            {t("landing.skills.titleFirst")}<br />
            {t("landing.skills.titleSecond")}
          </h2>
        </div>

        <div className="landing-skills-gallery">
          {LANDING_GALLERY.map((item, index) => (
            <div key={item.id} aria-hidden="true" className="landing-skills-frames" data-active={index === active}>
              {FRAME_NUMBERS.map((frame) => (
                <img
                  key={frame}
                  src={`/gallery/skills/${item.id}-${frame}.webp`}
                  alt=""
                  width={480}
                  height={640}
                  loading="lazy"
                  decoding="async"
                />
              ))}
            </div>
          ))}
          <div className="landing-skills-controls" role="group" aria-label={t("landing.skills.label")}>
            {LANDING_GALLERY.map((item, index) => {
              const selected = index === active
              const offset = (index - active + 1 + LANDING_GALLERY.length) % LANDING_GALLERY.length - 1
              const name = item.skill ? t(`skills.builtin.${item.skill.skill_id}.shortName`) : t(`landing.gallery.items.${item.id}.title`)
              return (
                <button
                  key={item.id}
                  type="button"
                  className="landing-skill-button"
                  data-offset={offset}
                  aria-current={selected || undefined}
                  aria-label={selected ? t("landing.skills.create", { name }) : name}
                  onClick={() => selected ? create(item) : selectSkill(index)}
                >
                  <span>{selected && item.skill && <span aria-hidden="true">/</span>}{name}</span>
                  {selected && <span className="landing-skill-arrow"><ArrowUp aria-hidden="true" /></span>}
                </button>
              )
            })}
          </div>
        </div>
      </div>
    </section>
  )
}
