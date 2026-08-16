import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, KeyboardEvent, MouseEvent, PointerEvent } from 'react'
import './jelly-pet.css'

const PET_WIDTH = 108
const PET_HEIGHT = 100
const EDGE_GAP = 18

type Point = { x: number; y: number }
type JellyStyle = CSSProperties & Record<`--${string}`, string | number>

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max)
}

function clampToViewport(point: Point): Point {
  return {
    x: clamp(point.x, EDGE_GAP, Math.max(EDGE_GAP, window.innerWidth - PET_WIDTH - EDGE_GAP)),
    y: clamp(point.y, EDGE_GAP, Math.max(EDGE_GAP, window.innerHeight - PET_HEIGHT - EDGE_GAP)),
  }
}

function initialPosition(): Point {
  return clampToViewport({
    x: window.innerWidth - PET_WIDTH - 30,
    y: window.innerHeight - PET_HEIGHT - 26,
  })
}

export default function JellyPet() {
  const [position, setPosition] = useState(initialPosition)
  const [eyeOffset, setEyeOffset] = useState<Point>({ x: 0, y: 0 })
  const [motion, setMotion] = useState({ stretchX: 1, stretchY: 1, rotation: 0 })
  const [dragging, setDragging] = useState(false)
  const [settling, setSettling] = useState(false)
  const [blinking, setBlinking] = useState(false)
  const [keyboardMode, setKeyboardMode] = useState(false)

  const positionRef = useRef(position)
  const dragRef = useRef({
    pointerId: -1,
    startPointer: { x: 0, y: 0 },
    startPosition: { x: 0, y: 0 },
    lastPointer: { x: 0, y: 0 },
    lastTime: 0,
    moved: false,
  })
  const settleTimerRef = useRef<number | null>(null)
  const blinkTimerRef = useRef<number | null>(null)

  const updatePosition = (next: Point) => {
    const clamped = clampToViewport(next)
    positionRef.current = clamped
    setPosition(clamped)
  }

  useEffect(() => {
    const handleResize = () => updatePosition(positionRef.current)
    const handlePointerLook = (event: globalThis.PointerEvent) => {
      if (dragRef.current.pointerId !== -1) return
      const centerX = positionRef.current.x + PET_WIDTH / 2
      const centerY = positionRef.current.y + PET_HEIGHT * 0.46
      const dx = event.clientX - centerX
      const dy = event.clientY - centerY
      const distance = Math.max(Math.hypot(dx, dy), 1)
      const strength = Math.min(distance / 140, 1)
      setEyeOffset({
        x: (dx / distance) * 3.2 * strength,
        y: (dy / distance) * 2.4 * strength,
      })
    }

    window.addEventListener('resize', handleResize)
    window.addEventListener('pointermove', handlePointerLook, { passive: true })
    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('pointermove', handlePointerLook)
    }
  }, [])

  useEffect(() => {
    const enterKeyboardMode = () => setKeyboardMode(true)
    const leaveKeyboardMode = () => setKeyboardMode(false)
    window.addEventListener('keydown', enterKeyboardMode, true)
    window.addEventListener('pointerdown', leaveKeyboardMode, true)
    return () => {
      window.removeEventListener('keydown', enterKeyboardMode, true)
      window.removeEventListener('pointerdown', leaveKeyboardMode, true)
    }
  }, [])

  useEffect(() => () => {
    if (settleTimerRef.current !== null) window.clearTimeout(settleTimerRef.current)
    if (blinkTimerRef.current !== null) window.clearTimeout(blinkTimerRef.current)
  }, [])

  const beginSettle = () => {
    if (settleTimerRef.current !== null) window.clearTimeout(settleTimerRef.current)
    setSettling(false)
    window.requestAnimationFrame(() => {
      setSettling(true)
      settleTimerRef.current = window.setTimeout(() => setSettling(false), 620)
    })
  }

  const blink = () => {
    if (blinkTimerRef.current !== null) window.clearTimeout(blinkTimerRef.current)
    setBlinking(false)
    window.requestAnimationFrame(() => {
      setBlinking(true)
      blinkTimerRef.current = window.setTimeout(() => setBlinking(false), 230)
    })
  }

  const handlePointerDown = (event: PointerEvent<HTMLButtonElement>) => {
    if (event.button !== 0) return
    event.currentTarget.setPointerCapture(event.pointerId)
    dragRef.current = {
      pointerId: event.pointerId,
      startPointer: { x: event.clientX, y: event.clientY },
      startPosition: positionRef.current,
      lastPointer: { x: event.clientX, y: event.clientY },
      lastTime: event.timeStamp,
      moved: false,
    }
    setDragging(true)
    setSettling(false)
  }

  const handlePointerMove = (event: PointerEvent<HTMLButtonElement>) => {
    if (dragRef.current.pointerId !== event.pointerId) return
    const totalX = event.clientX - dragRef.current.startPointer.x
    const totalY = event.clientY - dragRef.current.startPointer.y
    const deltaX = event.clientX - dragRef.current.lastPointer.x
    const deltaY = event.clientY - dragRef.current.lastPointer.y
    const elapsed = Math.max(event.timeStamp - dragRef.current.lastTime, 8)
    const velocityX = deltaX / elapsed
    const velocityY = deltaY / elapsed
    const speed = Math.hypot(velocityX, velocityY)
    const stretch = Math.min(speed * 0.095, 0.16)

    if (Math.hypot(totalX, totalY) > 3) dragRef.current.moved = true

    updatePosition({
      x: dragRef.current.startPosition.x + totalX,
      y: dragRef.current.startPosition.y + totalY,
    })
    setMotion({
      stretchX: 1 + stretch,
      stretchY: 1 - stretch * 0.58,
      rotation: clamp(velocityX * 4.5, -8, 8),
    })
    setEyeOffset({
      x: clamp(-velocityX * 1.8, -3.4, 3.4),
      y: clamp(-velocityY * 1.4, -2.6, 2.6),
    })

    dragRef.current.lastPointer = { x: event.clientX, y: event.clientY }
    dragRef.current.lastTime = event.timeStamp
  }

  const handlePointerEnd = (event: PointerEvent<HTMLButtonElement>) => {
    if (dragRef.current.pointerId !== event.pointerId) return
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    const target = event.currentTarget
    target.blur()
    window.requestAnimationFrame(() => target.blur())
    dragRef.current.pointerId = -1
    setDragging(false)
    setMotion({ stretchX: 1, stretchY: 1, rotation: 0 })
    setEyeOffset({ x: 0, y: 0 })
    if (dragRef.current.moved) beginSettle()
  }

  const handleClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.currentTarget.blur()
    if (!dragRef.current.moved) blink()
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    const movement: Record<string, Point> = {
      ArrowLeft: { x: -12, y: 0 },
      ArrowRight: { x: 12, y: 0 },
      ArrowUp: { x: 0, y: -12 },
      ArrowDown: { x: 0, y: 12 },
    }
    const delta = movement[event.key]
    if (!delta) return
    event.preventDefault()
    updatePosition({ x: positionRef.current.x + delta.x, y: positionRef.current.y + delta.y })
    beginSettle()
  }

  const jellyStyle: JellyStyle = {
    '--jelly-stretch-x': motion.stretchX,
    '--jelly-stretch-y': motion.stretchY,
    '--jelly-rotation': `${motion.rotation}deg`,
  }

  const eyeStyle = (baseX: number, baseY: number): CSSProperties => ({
    transform: `translate(${baseX + eyeOffset.x}px, ${baseY + eyeOffset.y}px)`,
  })

  return (
    <button
      type="button"
      draggable={false}
      className={`jelly-pet${dragging ? ' is-dragging' : ''}${keyboardMode ? ' is-keyboard-mode' : ''}`}
      style={{ transform: `translate3d(${position.x}px, ${position.y}px, 0)` }}
      aria-label="Move the MeSource jelly pet"
      title="Drag me"
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerEnd}
      onPointerCancel={handlePointerEnd}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
    >
      <svg viewBox="0 0 108 100" role="img" aria-label="A neon lime jelly with two eyes">
        <ellipse className="jelly-pet__shadow" cx="54" cy="89" rx="30" ry="5" />
        <g
          className={`jelly-pet__body${settling ? ' is-settling' : ''}${!dragging && !settling ? ' is-idle' : ''}`}
          style={jellyStyle}
        >
          <path
            className="jelly-pet__shape"
            d="M54 9C79 9 93 27 92 53C91 76 79 86 54 88C29 87 17 80 16 59C14 35 27 10 54 9Z"
          />
          <path
            className="jelly-pet__face"
            d="M54 27C70 27 80 36 80 53C80 67 72 73 54 74C36 73 28 68 28 54C27 39 37 28 54 27Z"
          />
          <path className="jelly-pet__shine" d="M31 30C36 20 47 16 58 17C46 19 38 24 33 35Z" />
          <g style={eyeStyle(40, 45)}>
            <circle className={`jelly-pet__eye${blinking ? ' is-blinking' : ''}`} r="5" />
          </g>
          <g style={eyeStyle(68, 45)}>
            <circle className={`jelly-pet__eye${blinking ? ' is-blinking' : ''}`} r="5" />
          </g>
        </g>
      </svg>
    </button>
  )
}
