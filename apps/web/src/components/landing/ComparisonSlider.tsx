import React, { useRef, useState } from "react"
import gsap from "gsap"
import { Draggable } from "gsap/Draggable"
import { InertiaPlugin } from "gsap/InertiaPlugin"
import { useGSAP } from "@gsap/react"
import { cn } from "@/lib/utils"
import { GripHorizontal, GripVertical } from "lucide-react"

/**
 * Comparison slider — source: ReactBits Pro (`comparison-slider`), owned copy.
 * Our extensions on top of the upstream source:
 *
 * 1. `beforeChildren` / `afterChildren` — ReactNode slots rendered inside the
 *    clipped panes (we put <video> + overlay DOM on each side, not <img>).
 * 2. ResizeObserver re-sync — the scroll-grow frame in VideoShowcase resizes
 *    the container continuously without a window resize, so position is
 *    re-derived from the percentage on every container size change (replaces
 *    the upstream window-resize listener).
 * 3. `handlePulse` — first-visit affordance ring, cleared on first drag.
 */

if (typeof window !== "undefined") {
  gsap.registerPlugin(Draggable, InertiaPlugin)
}

export interface ComparisonSliderProps {
  /** URL for the before image (left/top) — ignored when beforeChildren is set */
  beforeImage?: string
  /** URL for the after image (right/bottom) — ignored when afterChildren is set */
  afterImage?: string
  /** Custom content for the before pane (video, overlay DOM, …) */
  beforeChildren?: React.ReactNode
  /** Custom content for the after pane (video, overlay DOM, …) */
  afterChildren?: React.ReactNode
  /** Alt text for the before image */
  beforeAlt?: string
  /** Alt text for the after image */
  afterAlt?: string
  /** Initial position of the slider (0-100) */
  initialPosition?: number
  /** Orientation of the slider */
  orientation?: "horizontal" | "vertical"
  /** Enable inertia/momentum on drag */
  enableInertia?: boolean
  /** Enable drag on hover without clicking */
  dragOnHover?: boolean
  /** Auto-animate slider with smooth random movement */
  autoAnimate?: boolean
  /** Width of the divider line in pixels */
  dividerWidth?: number
  /** Show the handle with icon */
  showHandle?: boolean
  /** Size of the handle in pixels */
  handleSize?: number
  /** Custom icon component for the handle */
  handleIcon?: React.ReactNode
  /** Color of the divider line */
  dividerColor?: string
  /** Color of the handle background */
  handleColor?: string
  /** Pulse ring on the handle until the first drag (discovery affordance) */
  handlePulse?: boolean
  /** Show before/after labels */
  showLabels?: boolean
  /** Custom text for labels */
  labelText?: { before: string; after: string }
  /** Position of labels */
  labelPosition?: "top-left" | "top-right" | "bottom-left" | "bottom-right"
  /** Additional CSS classes for both labels */
  labelClassName?: string
  /** Additional CSS classes for before label */
  beforeLabelClassName?: string
  /** Additional CSS classes for after label */
  afterLabelClassName?: string
  /** Show percentage indicator */
  showPercentage?: boolean
  /** Position of percentage indicator */
  percentagePosition?: "top" | "bottom"
  /** Callback when drag starts */
  onDragStart?: () => void
  /** Callback when drag ends */
  onDragEnd?: () => void
  /** Callback when slider position changes */
  onPositionChange?: (position: number) => void
  /** Custom ARIA label */
  ariaLabel?: string
  /** Respect prefers-reduced-motion */
  reducedMotion?: boolean
  /** Additional CSS classes for the container */
  className?: string
  /** Additional CSS classes for images */
  imageClassName?: string
}

const ComparisonSlider: React.FC<ComparisonSliderProps> = ({
  beforeImage,
  afterImage,
  beforeChildren,
  afterChildren,
  beforeAlt = "Before",
  afterAlt = "After",
  initialPosition = 50,
  orientation = "horizontal",
  enableInertia = true,
  dragOnHover = false,
  autoAnimate = false,
  dividerWidth = 3,
  showHandle = true,
  handleSize = 48,
  handleIcon,
  dividerColor = "white",
  handleColor = "white",
  handlePulse = false,
  showLabels = false,
  labelText = { before: "Before", after: "After" },
  labelPosition = "top-left",
  labelClassName = "",
  beforeLabelClassName = "",
  afterLabelClassName = "",
  showPercentage = false,
  percentagePosition = "top",
  onDragStart,
  onDragEnd,
  onPositionChange,
  ariaLabel = "Image comparison slider",
  reducedMotion = false,
  className = "",
  imageClassName = "",
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const sliderRef = useRef<HTMLDivElement>(null)
  const beforeContainerRef = useRef<HTMLDivElement>(null)
  const afterContainerRef = useRef<HTMLDivElement>(null)
  const draggableInstanceRef = useRef<Draggable | null>(null)
  // Once the user has dragged, the idle float never resumes — the animation
  // is a discovery affordance, not a permanent behavior.
  const hasInteractedRef = useRef(false)
  const [isDragging, setIsDragging] = useState(false)
  const [currentPosition, setCurrentPosition] = useState(initialPosition)
  const [isReady, setIsReady] = useState(false)
  const autoAnimationRef = useRef<gsap.core.Tween | null>(null)
  const prefersReducedMotion =
    typeof window !== "undefined"
      ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false
  const shouldReduceMotion = reducedMotion || prefersReducedMotion

  const isHorizontal = orientation === "horizontal"

  const getLabelClasses = () => {
    const baseClasses =
      "absolute text-sm font-medium px-3 py-1.5 rounded backdrop-blur-sm bg-black/50 text-white pointer-events-none z-10"
    const positionClasses = {
      "top-left": "top-4 left-4",
      "top-right": "top-4 right-4",
      "bottom-left": "bottom-4 left-4",
      "bottom-right": "bottom-4 right-4",
    }
    return `${baseClasses} ${positionClasses[labelPosition]}`
  }

  useGSAP(
    () => {
      if (
        !sliderRef.current ||
        !containerRef.current ||
        !beforeContainerRef.current ||
        !afterContainerRef.current
      )
        return

      const container = containerRef.current
      const beforeContainer = beforeContainerRef.current
      const afterContainer = afterContainerRef.current
      const slider = sliderRef.current

      const containerRect = container.getBoundingClientRect()
      const initialPos = isHorizontal
        ? (initialPosition / 100) * containerRect.width
        : (initialPosition / 100) * containerRect.height

      if (isHorizontal) {
        gsap.set(slider, { x: initialPos, y: 0, immediateRender: true })
        gsap.set(beforeContainer, {
          clipPath: `inset(0px ${containerRect.width - initialPos}px 0px 0px)`,
          immediateRender: true,
        })
        gsap.set(afterContainer, {
          clipPath: `inset(0px 0px 0px ${initialPos}px)`,
          immediateRender: true,
        })
      } else {
        gsap.set(slider, { x: 0, y: initialPos, immediateRender: true })
        gsap.set(beforeContainer, {
          clipPath: `inset(0px 0px ${containerRect.height - initialPos}px 0px)`,
          immediateRender: true,
        })
        gsap.set(afterContainer, {
          clipPath: `inset(${initialPos}px 0px 0px 0px)`,
          immediateRender: true,
        })
      }

      setIsReady(true)

      const updateClip = (value: number, notify = true) => {
        const rect = container.getBoundingClientRect()
        const clampedValue = isHorizontal
          ? Math.max(0, Math.min(rect.width, value))
          : Math.max(0, Math.min(rect.height, value))

        const percentage = isHorizontal
          ? (clampedValue / rect.width) * 100
          : (clampedValue / rect.height) * 100

        setCurrentPosition(percentage)

        if (isHorizontal) {
          gsap.set(beforeContainer, {
            clipPath: `inset(0px ${rect.width - clampedValue}px 0px 0px)`,
          })
          gsap.set(afterContainer, {
            clipPath: `inset(0px 0px 0px ${clampedValue}px)`,
          })
        } else {
          gsap.set(beforeContainer, {
            clipPath: `inset(0px 0px ${rect.height - clampedValue}px 0px)`,
          })
          gsap.set(afterContainer, {
            clipPath: `inset(${clampedValue}px 0px 0px 0px)`,
          })
        }

        if (notify) onPositionChange?.(percentage)
      }

      const cleanupFunctions: (() => void)[] = []

      // The float tween runs in PERCENT space (via floatProxy) and converts
      // to pixels against the live rect every frame — a px-space tween would
      // drift off the clip seam while the container resizes mid-leg (the
      // scroll-grow frame in VideoShowcase resizes continuously).
      const floatProxy = { p: initialPosition }
      const animateSlider = () => {
        const rect = container.getBoundingClientRect()
        const rangePct = (50 / (isHorizontal ? rect.width : rect.height)) * 100
        const targetPct = 50 + (Math.random() - 0.5) * 2 * rangePct
        const duration = 1.5 + Math.random() * 1.5

        autoAnimationRef.current = gsap.to(floatProxy, {
          p: targetPct,
          duration,
          ease: "power1.inOut",
          overwrite: true,
          onUpdate: () => {
            const live = container.getBoundingClientRect()
            const px = isHorizontal
              ? (floatProxy.p / 100) * live.width
              : (floatProxy.p / 100) * live.height
            if (isHorizontal) {
              gsap.set(slider, { x: px })
            } else {
              gsap.set(slider, { y: px })
            }
            updateClip(px)
          },
          onComplete: animateSlider,
        })
      }

      if (autoAnimate && !shouldReduceMotion) {
        animateSlider()

        cleanupFunctions.push(() => {
          gsap.killTweensOf(slider)
          autoAnimationRef.current = null
        })
      }

      if (dragOnHover) {
        const handleMouseMove = (e: MouseEvent) => {
          if (autoAnimate && autoAnimationRef.current) {
            autoAnimationRef.current.kill()
            autoAnimationRef.current = null
          }

          const rect = container.getBoundingClientRect()
          const value = isHorizontal
            ? e.clientX - rect.left
            : e.clientY - rect.top

          updateClip(value)

          if (isHorizontal) {
            gsap.set(slider, { x: value })
          } else {
            gsap.set(slider, { y: value })
          }
        }

        const handleMouseEnter = () => {
          setIsDragging(true)
          onDragStart?.()
          if (autoAnimate && autoAnimationRef.current) {
            autoAnimationRef.current.kill()
            autoAnimationRef.current = null
          }
        }

        const handleMouseLeave = () => {
          setIsDragging(false)
          onDragEnd?.()
          if (autoAnimate) {
            animateSlider()
          }
        }

        container.addEventListener("mousemove", handleMouseMove)
        container.addEventListener("mouseenter", handleMouseEnter)
        container.addEventListener("mouseleave", handleMouseLeave)

        cleanupFunctions.push(() => {
          container.removeEventListener("mousemove", handleMouseMove)
          container.removeEventListener("mouseenter", handleMouseEnter)
          container.removeEventListener("mouseleave", handleMouseLeave)
        })
      }

      if (!dragOnHover) {
        const instances = Draggable.create(slider, {
          type: isHorizontal ? "x" : "y",
          bounds: container,
          inertia: enableInertia && !shouldReduceMotion,
          onDragStart: () => {
            hasInteractedRef.current = true
            if (autoAnimate && autoAnimationRef.current) {
              autoAnimationRef.current.kill()
              autoAnimationRef.current = null
            }
            setIsDragging(true)
            onDragStart?.()
          },
          onDrag: function () {
            const value = isHorizontal ? this.x : this.y
            updateClip(value)
          },
          onDragEnd: () => {
            setIsDragging(false)
            onDragEnd?.()
            if (autoAnimate && !hasInteractedRef.current) {
              animateSlider()
            }
          },
          onThrowUpdate: function () {
            const value = isHorizontal ? this.x : this.y
            updateClip(value)
          },
        })

        draggableInstanceRef.current = instances[0]

        cleanupFunctions.push(() => {
          if (draggableInstanceRef.current) {
            draggableInstanceRef.current.kill()
          }
        })
      }

      // Container-size re-sync (our addition): keeps the divider glued to its
      // percentage while the surrounding layout resizes the container — e.g.
      // the scroll-grow frame in VideoShowcase, window resizes, sidebars.
      const syncToContainerSize = () => {
        const rect = container.getBoundingClientRect()
        if (rect.width === 0 || rect.height === 0) return
        const posPx = isHorizontal
          ? (currentPosition / 100) * rect.width
          : (currentPosition / 100) * rect.height
        if (isHorizontal) {
          gsap.set(slider, { x: posPx })
        } else {
          gsap.set(slider, { y: posPx })
        }
        updateClip(posPx, false)
        draggableInstanceRef.current?.applyBounds(container)
      }
      const resizeObserver = new ResizeObserver(syncToContainerSize)
      resizeObserver.observe(container)
      cleanupFunctions.push(() => resizeObserver.disconnect())

      return () => {
        cleanupFunctions.forEach((cleanup) => cleanup())
      }
    },
    {
      scope: containerRef,
      dependencies: [
        initialPosition,
        orientation,
        enableInertia,
        dragOnHover,
        autoAnimate,
        beforeImage,
        afterImage,
      ],
    }
  )

  const defaultHandleIcon = isHorizontal ? (
    <GripVertical className="h-4 w-4" />
  ) : (
    <GripHorizontal className="h-4 w-4" />
  )

  return (
    <div
      className={cn(
        "relative h-full w-full overflow-hidden rounded-lg shadow-lg",
        !isReady && "opacity-0",
        className
      )}
      role="region"
      aria-label={ariaLabel}
    >
      <div
        ref={containerRef}
        className={cn(
          "relative h-full w-full overflow-hidden select-none",
          dragOnHover ? "cursor-default" : ""
        )}
      >
        <div
          ref={beforeContainerRef}
          className="absolute inset-0 h-full w-full transform-gpu will-change-[clip-path]"
        >
          {beforeChildren ??
            (beforeImage && (
              <img
                src={beforeImage}
                alt={beforeAlt}
                className={cn(
                  "h-full w-full object-cover pointer-events-none",
                  imageClassName
                )}
                draggable={false}
              />
            ))}
          {showLabels && (
            <div
              className={cn(
                getLabelClasses(),
                labelClassName,
                beforeLabelClassName
              )}
            >
              {labelText.before}
            </div>
          )}
        </div>

        <div
          ref={afterContainerRef}
          className="absolute inset-0 h-full w-full transform-gpu will-change-[clip-path]"
        >
          {afterChildren ??
            (afterImage && (
              <img
                src={afterImage}
                alt={afterAlt}
                className={cn(
                  "h-full w-full object-cover pointer-events-none",
                  imageClassName
                )}
                draggable={false}
              />
            ))}
          {showLabels && (
            <div
              className={cn(
                getLabelClasses(),
                labelClassName,
                afterLabelClassName
              )}
            >
              {labelText.after}
            </div>
          )}
        </div>

        <div
          ref={sliderRef}
          className={cn(
            "absolute z-10 will-change-transform",
            dragOnHover
              ? "cursor-crosshair pointer-events-none"
              : autoAnimate
                ? isDragging
                  ? "cursor-grabbing"
                  : "cursor-grab"
                : isDragging
                  ? "cursor-grabbing"
                  : "cursor-grab",
            isHorizontal ? "top-0 h-full" : "left-0 w-full"
          )}
        >
          <div
            className={cn(
              "absolute",
              isHorizontal ? "top-0 left-1/2 h-full" : "top-1/2 left-0 w-full"
            )}
            style={{
              [isHorizontal ? "width" : "height"]: `${dividerWidth}px`,
              background: `linear-gradient(to top, transparent 10%, ${dividerColor} 30%, ${dividerColor} 70%, transparent 90%)`,
              transform: isHorizontal
                ? `translateX(-${dividerWidth / 2}px)`
                : `translateY(-${dividerWidth / 2}px)`,
            }}
          />

          {showHandle && (
            <div
              className={cn(
                "absolute top-1/2 left-1/2 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full shadow-lg transition-transform",
                isDragging ? "scale-110" : "scale-100"
              )}
              style={{
                width: `${handleSize}px`,
                height: `${handleSize}px`,
                backgroundColor: handleColor,
                boxShadow: `0 0 60px ${dividerColor}, 0 0 50px ${dividerColor}`,
                color:
                  handleColor === "#ffffff" ||
                  handleColor === "white" ||
                  handleColor === "#fff"
                    ? "#000"
                    : "#fff",
              }}
            >
              {handlePulse && !isDragging && (
                <span
                  className="absolute inset-0 animate-ping rounded-full opacity-40"
                  style={{ backgroundColor: handleColor }}
                  aria-hidden="true"
                />
              )}
              <span className="relative">{handleIcon || defaultHandleIcon}</span>
            </div>
          )}
        </div>

        {showPercentage && percentagePosition === "top" && (
          <div className="pointer-events-none absolute top-4 left-1/2 z-20 -translate-x-1/2 rounded-full bg-black/70 px-2 py-1 text-xs font-medium text-white backdrop-blur-sm">
            {Math.round(currentPosition)}%
          </div>
        )}

        {showPercentage && percentagePosition === "bottom" && (
          <div className="pointer-events-none absolute bottom-4 left-1/2 z-20 -translate-x-1/2 rounded-full bg-black/70 px-2 py-1 text-xs font-medium text-white backdrop-blur-sm">
            {Math.round(currentPosition)}%
          </div>
        )}
      </div>
    </div>
  )
}

export default ComparisonSlider
