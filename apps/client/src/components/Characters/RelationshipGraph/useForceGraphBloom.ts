import { useEffect, useRef, type RefObject } from 'react'
import * as THREE from 'three'
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js'
import type { ForceGraphMethods } from 'react-force-graph-3d'
import type { ForceGraphLink, ForceGraphNode } from './forceGraphPaint'

/**
 * 轻度 Bloom：只给星点加柔光，避免点击后单节点占满屏幕。
 * 参数刻意低于官方 demo（strength 4），防止「巨大光球」突兀感。
 */
export function useForceGraphBloom(
  fgRef: RefObject<ForceGraphMethods<ForceGraphNode, ForceGraphLink> | undefined>,
  size: { w: number; h: number },
) {
  const bloomRef = useRef<UnrealBloomPass | null>(null)
  const addedRef = useRef(false)

  useEffect(() => {
    const fg = fgRef.current
    if (!fg || addedRef.current || size.w < 10) return

    const composer = fg.postProcessingComposer?.()
    if (!composer) return

    const bloom = new UnrealBloomPass(
      new THREE.Vector2(size.w, size.h),
      0.65,
      0.45,
      0.62,
    )
    composer.addPass(bloom)
    bloomRef.current = bloom
    addedRef.current = true
  }, [fgRef, size.w, size.h])

  return bloomRef
}
