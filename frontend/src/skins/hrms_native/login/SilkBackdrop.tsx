/**
 * Adapted from React Bits "Silk" (https://reactbits.dev, MIT + Commons Clause): a slow,
 * satin-like fold rendered in a single brand colour. Loaded lazily by HeroBackdrop.
 */
import { forwardRef, useLayoutEffect, useMemo, useRef, type MutableRefObject } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Color, type IUniform, type Mesh, type ShaderMaterial } from 'three';

const vertexShader = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const fragmentShader = `
varying vec2 vUv;
uniform float uTime;
uniform vec3  uColor;
uniform float uSpeed;
uniform float uScale;
uniform float uRotation;
uniform float uNoiseIntensity;
const float e = 2.71828182845904523536;

float noise(vec2 texCoord) {
  vec2 r = e * sin(e * texCoord);
  return fract(r.x * r.y * (1.0 + texCoord.x));
}

vec2 rotateUvs(vec2 uv, float angle) {
  float c = cos(angle);
  float s = sin(angle);
  return mat2(c, -s, s, c) * uv;
}

void main() {
  float rnd = noise(gl_FragCoord.xy);
  vec2 tex = rotateUvs(vUv * uScale, uRotation) * uScale;
  float tOffset = uSpeed * uTime;
  tex.y += 0.03 * sin(8.0 * tex.x - tOffset);
  float pattern = 0.6 + 0.4 * sin(5.0 * (tex.x + tex.y + cos(3.0 * tex.x + 5.0 * tex.y) + 0.02 * tOffset) + sin(20.0 * (tex.x + tex.y - 0.1 * tOffset)));
  vec3 result = uColor * pattern - vec3(rnd / 15.0 * uNoiseIntensity);
  gl_FragColor = vec4(clamp(result, 0.0, 1.0), 1.0);
}
`;

type SilkUniforms = { uSpeed: IUniform<number>; uScale: IUniform<number>; uNoiseIntensity: IUniform<number>; uColor: IUniform<Color>; uRotation: IUniform<number>; uTime: IUniform<number> };

const SilkPlane = forwardRef<Mesh, { uniforms: SilkUniforms }>(function SilkPlane({ uniforms }, ref) {
  const { viewport } = useThree();
  useLayoutEffect(() => {
    (ref as MutableRefObject<Mesh | null>).current?.scale.set(viewport.width, viewport.height, 1);
  }, [ref, viewport]);
  useFrame((_state, delta) => {
    const mesh = (ref as MutableRefObject<Mesh | null>).current;
    if (mesh) ((mesh.material as ShaderMaterial).uniforms as SilkUniforms).uTime.value += 0.1 * delta;
  });
  return <mesh ref={ref}>
    <planeGeometry args={[1, 1, 1, 1]} />
    <shaderMaterial uniforms={uniforms} vertexShader={vertexShader} fragmentShader={fragmentShader} />
  </mesh>;
});

export default function SilkBackdrop({ color = '#2f6fd6', speed = 3.2, scale = 1, rotation = 0.35, noiseIntensity = 0.6 }: { color?: string; speed?: number; scale?: number; rotation?: number; noiseIntensity?: number }) {
  const mesh = useRef<Mesh>(null);
  const uniforms = useMemo<SilkUniforms>(() => ({
    uSpeed: { value: speed }, uScale: { value: scale }, uNoiseIntensity: { value: noiseIntensity },
    uColor: { value: new Color(color) }, uRotation: { value: rotation }, uTime: { value: 0 },
  }), [color, speed, scale, rotation, noiseIntensity]);
  return <div className="hrms-login-canvas"><Canvas dpr={[1, 1.5]} gl={{ powerPreference: 'low-power', antialias: false }}><SilkPlane ref={mesh} uniforms={uniforms} /></Canvas></div>;
}
