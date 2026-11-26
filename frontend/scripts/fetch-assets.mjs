// Fetches upstream game assets (sprites, sounds) at build time instead of
// redistributing them in this repository. See ATTRIBUTION.md.
// Source: gorisanson/pikachu-volleyball @ pinned commit, verified by SHA-256.
import { createHash } from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const UPSTREAM_COMMIT = '6bc096ad9e25137ae27eb536a6eac1d056be7506'
const BASE = `https://raw.githubusercontent.com/gorisanson/pikachu-volleyball/${UPSTREAM_COMMIT}/src/resources/assets`
const PUBLIC_ASSETS = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'assets')

// [local path under public/assets, upstream path under src/resources/assets, sha256]
const FILES = [
  ['sprite_sheet.png', 'images/sprite_sheet.png', 'eadd6aeb83cb44567dbdbe723671e7d3bf8c556faf382a27d3a8fa4c087ffbf7'],
  ['sprite_sheet.json', 'images/sprite_sheet.json', '0f0290fe08d5c5f6fec1700800798298d3fff0482185c0a8aa3aa3782c84a6a4'],
  ['sounds/WAVE140_1.wav', 'sounds/WAVE140_1.wav', '7d870fc1e1ebb13c88b8af85e485411fd3cc820628c2ccf78e236516e70ced42'],
  ['sounds/WAVE141_1.wav', 'sounds/WAVE141_1.wav', 'ee88b87d33b7ebb5e0fe1822de11b4490ce78ead81c55a42ee37d02d86a22ade'],
  ['sounds/WAVE142_1.wav', 'sounds/WAVE142_1.wav', 'b66e64831390ab771fe2e6b4aea37a3715db1c8d340625382044e75250fc9899'],
  ['sounds/WAVE143_1.wav', 'sounds/WAVE143_1.wav', 'c8965defd9e5d1b0cb9362b4cd132282f297d09860a768e7ca5e38389b0fea46'],
  ['sounds/WAVE144_1.wav', 'sounds/WAVE144_1.wav', 'd583e1f5a080a3f0c965c48934c17f48937a730047bc6efe80fddb1a9281d355'],
  ['sounds/WAVE145_1.wav', 'sounds/WAVE145_1.wav', '8ec56a6fe8558b88359adb0870c1ee854b5026a5d6ef59d09c1dbe9080ff8387'],
  ['sounds/WAVE146_1.wav', 'sounds/WAVE146_1.wav', '90180d6a8f284281198abed24e0a3c10bf9dcee19b586e2fa754a62ea0ca415e'],
  ['sounds/bgm.mp3', 'sounds/bgm.mp3', '0f407feb7897595d479f50bb58dbf414227c17c1ddf1a07c61baba32fcc74c16'],
]

const sha256 = (buf) => createHash('sha256').update(buf).digest('hex')

async function ensure([local, upstream, expected]) {
  const dest = join(PUBLIC_ASSETS, local)
  try {
    if (sha256(await readFile(dest)) === expected) return 'ok'
  } catch {
    // missing; download below
  }
  const res = await fetch(`${BASE}/${upstream}`)
  if (!res.ok) throw new Error(`download failed ${res.status}: ${upstream}`)
  const buf = Buffer.from(await res.arrayBuffer())
  const got = sha256(buf)
  if (got !== expected) throw new Error(`checksum mismatch for ${upstream}: ${got}`)
  await mkdir(dirname(dest), { recursive: true })
  await writeFile(dest, buf)
  return 'fetched'
}

const results = await Promise.all(FILES.map(ensure))
const fetched = results.filter((r) => r === 'fetched').length
console.log(`[fetch-assets] ${FILES.length} upstream assets ready (${fetched} downloaded)`)
