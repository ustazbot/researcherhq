import { useEffect, useRef, useId } from 'react'

export function TurnstileWidget({ onVerify, onExpire }) {
  const containerRef = useRef(null)
  const widgetIdRef = useRef(null)
  const elId = useId()

  useEffect(() => {
    let cancelled = false

    function render() {
      if (cancelled || !window.turnstile || !containerRef.current) return
      widgetIdRef.current = window.turnstile.render(containerRef.current, {
        sitekey: import.meta.env.VITE_TURNSTILE_SITE_KEY,
        callback: (token) => onVerify(token),
        'expired-callback': () => onExpire?.(),
        'error-callback': () => onExpire?.(),
      })
    }

    if (window.turnstile) {
      render()
    } else {
      const interval = setInterval(() => {
        if (window.turnstile) {
          clearInterval(interval)
          render()
        }
      }, 100)
      return () => clearInterval(interval)
    }

    return () => {
      cancelled = true
      if (window.turnstile && widgetIdRef.current != null) {
        window.turnstile.remove(widgetIdRef.current)
      }
    }
  }, [])

  return <div id={`turnstile-${elId}`} ref={containerRef} style={{ margin: '12px 0' }} />
}
