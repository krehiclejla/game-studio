import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Cube, Expand, ExternalLink, Eye, Folder, Group, History, Home, ImageSquare, Menu, Pencil, Play, Plus, Reload, Undo, User, X } from '@openai/apps-sdk-ui/components/Icon'
import AssetsPanel from './AssetsPanel.jsx'
import { readModel } from './ModelView.jsx'
import { updateShared } from './aiJobs.js'
import CharactersPanel from './CharactersPanel.jsx'
import { UseInGameSheet } from './libraryUi.jsx'
import { audioKey, buildGameDocument, mergeArt, relayVisibility, withAudio, withLibrary } from './gameRuntime.js'
import { useEngine } from './engine.js'
import { studioAgentPrompt } from './agentPrompt.js'
import SceneEditor, { SCENE_CSS } from './SceneEditor.jsx'
import { REQUESTS_CSS, RequestsSheet, askMessage, noteMessage, usePlaytestNotes, useRequestBoard } from './requestsBoard.jsx'
import { EMPTY_SCENE, sceneDocument } from './sceneRuntime.js'
import { MODEL_CATALOG, blobToBase64, checkModelFile, fetchCatalogModel } from './models.js'
import { createVoice } from './voice.js'
import { modelFor, setModelToken } from './aiModel.js'

const CSS = `
* { box-sizing: border-box; }
.gs-root { height: 100%; min-height: 100%; display: flex; flex-direction: column; color: var(--text); background: var(--bg); font-family: var(--font); }
.gs-top { display: flex; align-items: center; gap: 10px 12px; padding: 12px 16px 8px; flex-wrap: wrap; }
.gs-top .gs-new { margin-left: auto; }
.gs-gd-selected { position: absolute; left: 12px; right: 12px; bottom: 12px; z-index: 6; display: flex; align-items: center; gap: 8px; padding: 8px 8px 8px 12px; border-radius: 14px; background: rgba(12,14,24,.82); color: #fff; font-size: 13px; backdrop-filter: blur(6px); }
.gs-gd-selected span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gs-gd-selected svg { width: 16px; height: 16px; flex: none; }
.gs-delete-game { flex: none; min-height: 40px; padding: 0 12px; border-radius: 999px; border: 1px solid transparent; background: transparent; color: var(--muted); font: inherit; font-size: 13px; cursor: pointer; }
.gs-delete-game:hover, .gs-delete-game:focus-visible { color: #e5484d; border-color: rgba(229,72,77,.4); }
.gs-confirm-delete { flex: none; display: inline-flex; align-items: center; gap: 8px; font-size: 13px; color: var(--muted); }
.gs-btn--danger { background: #e5484d; color: #fff; border-color: #e5484d; }
.gs-share-link { display: flex; gap: 8px; margin: 4px 0 12px; }
.gs-share-link input { flex: 1 1 auto; min-width: 0; min-height: 44px; padding: 0 12px; border: 1px solid var(--border); border-radius: 12px; background: var(--bg); color: var(--text); font: inherit; font-size: 14px; }
.gs-title { flex: 1 1 auto; min-width: 0; margin: 0; font-size: 17px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gs-brand { display: flex; align-items: center; gap: 10px; flex: none; }
.gs-logo { width: 32px; height: 32px; border-radius: 10px; background: conic-gradient(from 200deg, #ffd84a, #ff7a59, #7c6cff, #3dd6b5, #ffd84a); box-shadow: 0 4px 14px rgba(124,108,255,.35); }
.gs-brand h1 { margin: 0; font-size: 17px; letter-spacing: -.01em; }
.gs-games { display: flex; gap: 8px; overflow-x: auto; scrollbar-width: none; flex: 1; padding: 2px; }
.gs-games::-webkit-scrollbar { display: none; }
.gs-games[hidden] { display: none; }
.gs-game-chip { flex: none; min-height: 40px; padding: 0 14px; border-radius: 999px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font: inherit; font-size: 14px; cursor: pointer; }
.gs-game-chip[aria-pressed="true"] { background: var(--text); color: var(--bg); border-color: var(--text); font-weight: 600; }
.gs-new { flex: none; display: inline-flex; align-items: center; gap: 6px; min-height: 40px; padding: 0 14px; border-radius: 999px; border: 1px dashed var(--border); background: transparent; color: var(--text); font: inherit; font-size: 14px; cursor: pointer; }
.gs-tabs { display: flex; gap: 4px; margin: 0 16px 10px; padding: 4px; border-radius: 14px; background: var(--surface); }
.gs-root.is-hosted .gs-tabs { margin-top: 10px; }
.gs-root.is-host-tabs .gs-body { padding-top: 10px; }
.gs-tab { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 40px; border: 0; border-radius: 10px; background: transparent; color: var(--muted); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.gs-tab[aria-selected="true"] { background: var(--bg); color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,.12); }
.gs-body { flex: 1; min-height: 0; display: flex; padding: 0 16px 16px; gap: 16px; }
.gs-panel { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.gs-panel[hidden] { display: none; }
.gs-stage { position: relative; flex: 1; min-height: 280px; border-radius: 18px; overflow: hidden; background: #0b1020; box-shadow: inset 0 0 0 1px rgba(255,255,255,.06); }
.gs-stage iframe { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; display: block; }
.gs-stage-empty { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; padding: 24px; color: #cfd6ff; }
.gs-stage-empty h2 { margin: 0 0 6px; font-size: 22px; color: #fff; }
.gs-stage-empty p { margin: 0 0 16px; color: #aab3e6; }
.gs-bar { display: flex; align-items: center; gap: 8px; padding: 10px 2px 0; flex-wrap: wrap; }
.gs-bar-title { flex: 1; min-width: 120px; }
.gs-bar-title strong { display: block; font-size: 15px; }
.gs-bar-title span { display: block; color: var(--muted); font-size: 13px; line-height: 1.35; }
.gs-btn { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 44px; padding: 0 14px; border-radius: 12px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.gs-btn--primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.gs-btn svg, .gs-tab svg, .gs-new svg, .gs-icon-btn svg { width: 18px; height: 18px; }
.gs-icon-btn { display: inline-grid; place-items: center; width: 44px; height: 44px; border-radius: 12px; border: 0; background: transparent; color: var(--muted); cursor: pointer; }
.gs-btn:focus-visible, .gs-tab:focus-visible, .gs-chip:focus-visible, .gs-game-chip:focus-visible, .gs-new:focus-visible, .gs-icon-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.gs-banner { margin-top: 10px; padding: 10px 12px; border-radius: 12px; background: color-mix(in srgb, #ff5a5a 14%, var(--surface)); color: var(--text); font-size: 13px; display: flex; gap: 10px; align-items: center; }
.gs-banner p { margin: 0; flex: 1; }
.gs-banner--info { background: color-mix(in srgb, var(--accent) 14%, var(--surface)); }
.gs-chat { flex: 1; min-height: 360px; border-radius: 18px; overflow: hidden; background: var(--surface); }
.gs-assets { display: flex; flex-direction: column; gap: 14px; overflow-y: auto; padding-bottom: 8px; }
.gs-card { padding: 16px; border-radius: 18px; background: var(--surface); }
.gs-card-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.gs-card-head h3 { margin: 0; font-size: 16px; }
.gs-card-head svg { width: 20px; height: 20px; color: var(--accent); }
.gs-chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.gs-chip { min-height: 36px; padding: 0 12px; border-radius: 999px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: inherit; font-size: 13px; text-transform: capitalize; cursor: pointer; }
.gs-chip[aria-pressed="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
.gs-chips--quiet .gs-chip { min-height: 32px; font-size: 12px; }
.gs-maker { display: flex; gap: 14px; align-items: stretch; flex-wrap: wrap; }
.gs-preview { width: 132px; height: 132px; flex: none; display: grid; place-items: center; border-radius: 16px; background: repeating-conic-gradient(#1a2040 0 25%, #141a36 0 50%) 0 0 / 16px 16px; }
.gs-preview img { max-width: 104px; max-height: 104px; image-rendering: pixelated; }
.gs-preview--tile { background-size: 64px 64px; image-rendering: pixelated; }
.gs-maker-controls { flex: 1; min-width: 180px; display: flex; flex-direction: column; gap: 8px; }
.gs-maker-controls--row { flex-direction: row; flex-wrap: wrap; align-items: flex-end; }
.gs-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); flex: 1; min-width: 120px; }
.gs-field input { min-height: 44px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: inherit; font-size: 15px; }
.gs-library { list-style: none; margin: 14px 0 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 8px; }
.gs-asset { position: relative; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 10px 6px 6px; border-radius: 12px; background: var(--bg); font-size: 12px; }
.gs-asset img { width: 48px; height: 48px; object-fit: contain; image-rendering: pixelated; }
.gs-asset .gs-icon-btn { width: 36px; height: 36px; }
.gs-library--sounds { grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
.gs-asset--sound { flex-direction: row; padding: 4px; }
.gs-asset--sound span { flex: 1; font-size: 14px; }
.gs-models { list-style: none; margin: 0 0 12px; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.gs-model { display: flex; align-items: center; gap: 12px; padding: 12px; border-radius: 14px; background: var(--bg); }
.gs-model > div { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.gs-model strong { font-size: 14px; }
.gs-model span, .gs-model small { color: var(--muted); font-size: 12px; line-height: 1.4; }
.gs-tag { display: inline-block; margin-left: 4px; padding: 1px 7px; border-radius: 999px; background: var(--surface-2, var(--surface)); color: var(--text) !important; font-size: 11px !important; font-family: ui-monospace, monospace; }
.gs-added { display: inline-flex; align-items: center; gap: 4px; color: var(--accent) !important; font-weight: 600; font-size: 13px !important; }
.gs-added svg { width: 16px; height: 16px; }
.gs-btn:disabled { opacity: .55; cursor: default; }
.gs-app-status { color: var(--muted); font-size: 13px; }
.gs-hint--tight { margin: 0 0 12px !important; }
.gs-hint { margin: 12px 0 0; color: var(--muted); font-size: 13px; line-height: 1.45; }
.gs-error { margin: 10px 0 0; color: #ff6b6b; font-size: 13px; }
.gs-versions { margin-top: 10px; padding: 12px; border-radius: 14px; background: var(--surface); }
.gs-versions h3 { margin: 0 0 8px; font-size: 14px; }
.gs-versions ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; max-height: 180px; overflow-y: auto; }
.gs-versions li { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 13px; }
.gs-root.is-focus .gs-top, .gs-root.is-focus .gs-tabs, .gs-root.is-focus .gs-bar, .gs-root.is-focus .gs-side, .gs-root.is-focus .gs-banner, .gs-root.is-focus .gs-versions { display: none; }
.gs-root.is-focus .gs-body { padding: 0; }
.gs-root.is-focus .gs-stage { border-radius: 0; }
.gs-exit { position: absolute; top: max(10px, var(--mobius-safe-top, 0px)); right: max(10px, var(--mobius-safe-right, 0px)); z-index: 2; width: 44px; height: 44px; border-radius: 50%; border: 0; background: rgba(0,0,0,.45); color: #fff; display: grid; place-items: center; cursor: pointer; }
.gs-sheet-scrim { position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,.45); display: flex; align-items: flex-end; justify-content: center; }
.gs-sheet { width: 100%; max-width: 640px; max-height: 92%; overflow-y: auto; background: var(--bg); color: var(--text); border-radius: 22px 22px 0 0; padding: 18px 18px max(18px, var(--mobius-safe-bottom, 0px)); box-shadow: 0 -10px 40px rgba(0,0,0,.35); }
@media (min-width: 720px) { .gs-sheet-scrim { align-items: center; } .gs-sheet { border-radius: 22px; } }
.gs-sheet-head { display: flex; align-items: center; justify-content: space-between; }
.gs-sheet-head h2 { margin: 0; font-size: 20px; }
.gs-sheet-lead { margin: 4px 0 14px; color: var(--muted); font-size: 14px; line-height: 1.45; }
.gs-sheet-label { margin: 16px 0 8px; font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.gs-genres { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 8px; }
.gs-genre { position: relative; display: flex; flex-direction: column; gap: 4px; min-height: 84px; padding: 12px 14px; border-radius: 16px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font: inherit; text-align: left; cursor: pointer; }
.gs-genre strong { display: inline-flex; align-items: center; gap: 6px; font-size: 15px; }
.gs-genre strong svg { width: 16px; height: 16px; }
.gs-genre span { color: var(--muted); font-size: 12.5px; line-height: 1.4; }
.gs-genre[aria-checked="true"] { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent) inset; }
.gs-genre-check { position: absolute; top: 10px; right: 10px; width: 18px; height: 18px; color: var(--accent); }
.gs-chip--style { display: inline-flex; flex-direction: column; align-items: flex-start; min-height: 48px; padding: 6px 14px; border-radius: 14px; text-transform: none; font-weight: 600; }
.gs-chip--style small { font-weight: 400; font-size: 11.5px; opacity: .8; }
.gs-field--wide { margin-top: 14px; }
.gs-sheet-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
.gs-together-steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; counter-reset: step; }
.gs-together-steps li { display: grid; grid-template-columns: 30px 1fr; gap: 12px; align-items: start; padding: 12px; border-radius: 14px; background: var(--surface); border: 1px solid var(--border); counter-increment: step; }
.gs-together-steps li::before { content: counter(step); display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; background: color-mix(in srgb, var(--accent) 22%, transparent); color: var(--accent); font-weight: 700; font-size: 14px; }
.gs-together-steps b { display: block; font-size: 15px; margin-bottom: 2px; }
.gs-together-steps span { color: var(--muted); font-size: 13.5px; line-height: 1.45; }
.gs-genre:focus-visible, .gs-chip--style:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.gs-side { display: none; }
@media (max-width: 719px) { .gs-games { order: 3; flex: 1 1 100%; } }
@media (min-width: 960px) {
  .gs-tabs { max-width: 520px; }
  .gs-panel[data-panel="play"] { flex: 1.35; }
  .gs-side { display: flex; flex-direction: column; flex: 1; min-width: 340px; max-width: 520px; min-height: 0; }
  .gs-side[hidden] { display: none; }
  .gs-side .gs-chat { flex: 1; }
}
.gs-panel--page { overflow-y: auto; }
.gs-library-page { width: 100%; max-width: 860px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; padding-bottom: 12px; }
.gs-sheet-label { margin: 14px 0 8px; font-size: 12px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.gs-types { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 8px; }
.gs-type { position: relative; display: flex; flex-direction: column; gap: 3px; min-height: 64px; padding: 10px 12px; border-radius: 14px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: inherit; text-align: left; cursor: pointer; }
.gs-type strong { font-size: 15px; }
.gs-type span { color: var(--muted); font-size: 12.5px; line-height: 1.35; }
.gs-type[aria-checked="true"] { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent) inset; }
.gs-type:focus-visible, .gs-char-card:focus-visible, .gs-suggestion:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.gs-char-grid { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.gs-char { border-radius: 16px; background: var(--bg); overflow: hidden; }
.gs-char.is-open { grid-column: 1 / -1; }
.gs-char-card { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 12px 8px 10px; border: 0; background: transparent; color: var(--text); font: inherit; cursor: pointer; }
.gs-char-card strong { font-size: 14px; }
.gs-char.is-open .gs-char-card { flex-direction: row; justify-content: flex-start; gap: 12px; padding: 12px 14px; }
.gs-sheet-preview { width: 112px; height: 112px; background-repeat: no-repeat; border-radius: 12px; background-color: color-mix(in srgb, var(--surface) 70%, transparent); }
.gs-char.is-open .gs-sheet-preview { width: 168px; height: 168px; }
.gs-sheet-preview.is-pixel { image-rendering: pixelated; }
.gs-char-detail { padding: 0 14px 14px; }
.gs-char-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.gs-suggestions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; max-width: 440px; margin: 0 auto; }
.gs-suggestion { min-height: 44px; padding: 0 14px; border-radius: 999px; border: 1px solid rgba(255,255,255,.22); background: rgba(255,255,255,.08); color: #fff; font: inherit; font-size: 14px; cursor: pointer; }
.gs-suggestion:hover { background: rgba(255,255,255,.16); }
.gs-new:disabled { opacity: .6; }
/* Phones: room for the game picker, finger-sized controls, the chat's box on screen. */
@media (max-width: 559px) {
  .gs-logo { display: none; }
  .gs-top { padding: 8px 12px 6px; gap: 8px; }
  .gs-new { padding: 0 12px; min-height: 44px; }
  .gs-tabs { margin: 0 12px 8px; }
  .gs-tab { min-height: 44px; font-size: 13px; gap: 4px; }
  .gs-body { padding: 0 12px 12px; }
  .gs-build-chat { min-height: 230px; margin-top: 8px; }
}
@media (max-width: 959px) {
  .gs-panel--build .gs-stage { flex: 0 0 auto; height: clamp(170px, 32dvh, 460px); min-height: 0; }
  .gs-panel--build .gs-stage-empty h2 { font-size: 18px; }
  .gs-panel--build .gs-stage-empty p { margin-bottom: 10px; font-size: 13px; }
  .gs-suggestion { min-height: 36px; padding: 0 12px; font-size: 13px; }
  .gs-panel--build:not(:has(.gs-build-chat)) .gs-stage { flex: 1; height: auto; min-height: 280px; }
  .gs-panel--build .gs-bar { padding-top: 8px; }
  .gs-panel--build .gs-bar-title span { display: none; }
  .gs-build-chat { flex: 1; min-height: 220px; display: flex; flex-direction: column; margin-top: 6px; }
  .gs-panel--build .gs-bar .gs-btn { min-height: 40px; }
  .gs-top { padding-bottom: 6px; }
  .gs-tabs { margin-bottom: 8px; }
  .gs-build-chat .gs-chat { min-height: 0; }
}
.gs-root.is-focus .gs-build-chat { display: none; }
.gs-root.is-focus .gs-panel--build .gs-stage { flex: 1; height: auto; }
.gs-spinner { width: 34px; height: 34px; margin: 0 auto 14px; border-radius: 50%; border: 3px solid rgba(255,255,255,.18); border-top-color: #fff; animation: gs-spin 1s linear infinite; }
@keyframes gs-spin { to { transform: rotate(360deg); } }
.gs-chip--plain { text-transform: none; }
.gs-moves { margin: 4px 0 12px; }
.gs-moves-sheet { display: grid; gap: 12px; padding: 12px; border: 1px solid var(--border); border-radius: 14px; background: var(--surface-2); }
.gs-moves-group h3 { margin: 0 0 6px; font-size: 12px; font-weight: 600; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); }
.gs-moves .gs-chip:disabled { opacity: .45; cursor: default; }
.gs-field--area { margin-bottom: 10px; }
.gs-field textarea { min-height: 64px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: inherit; font-size: 15px; resize: vertical; }
.gs-field input:focus-visible, .gs-field textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.gs-jobs { list-style: none; margin: 12px 0 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.gs-job { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 6px 12px; border-radius: 12px; background: var(--bg); font-size: 14px; }
.gs-job > span:nth-child(2) { flex: 1; }
.gs-job-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); flex: none; }
.gs-job--drawing .gs-job-dot { animation: gs-pulse 1.2s ease-in-out infinite; }
.gs-job--failed .gs-job-dot { background: #ff6b6b; }
@keyframes gs-pulse { 50% { opacity: .3; transform: scale(.7); } }
.gs-card-head--sub { margin: 18px 0 4px; }
.gs-card-head--sub h3 { flex: 1; font-size: 15px; }
.gs-btn--small { min-height: 36px; padding: 0 10px; font-size: 13px; }
.gs-asset-actions { display: flex; }
.gs-asset img:not(.is-pixel) { image-rendering: auto; }
@media (prefers-reduced-motion: reduce) { .gs-spinner, .gs-job--drawing .gs-job-dot { animation: none; } }
.gs-head-action { margin-left: auto; }
.gs-card-head h3 { margin: 0; }
.gs-new-char { margin: 4px 0 14px; padding: 14px; border-radius: 16px; background: var(--bg); }
.gs-drafts { list-style: none; margin: 0 0 16px; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.gs-draft { display: flex; gap: 12px; padding: 12px; border-radius: 16px; background: var(--bg); border: 1px solid color-mix(in srgb, var(--accent) 35%, var(--border)); }
.gs-draft--failed { border-color: var(--border); }
.gs-draft-art { flex: none; width: 128px; height: 128px; border-radius: 12px; display: grid; place-items: center; background: repeating-conic-gradient(#1a2040 0 25%, #141a36 0 50%) 0 0 / 16px 16px; }
.gs-draft-art img { width: 120px; height: 120px; object-fit: contain; }
.gs-draft-art .gs-spinner { margin: 0; }
.gs-draft-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.gs-draft-body > span, .gs-draft-desc { color: var(--muted); font-size: 13px; line-height: 1.4; }
.gs-draft-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 4px; }
.gs-draft-change textarea { width: 100%; min-height: 56px; padding: 8px 10px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); color: var(--text); font: inherit; font-size: 14px; }
.gs-empty-gallery { padding: 18px 4px; text-align: center; color: var(--muted); font-size: 14px; line-height: 1.5; }
.gs-empty-gallery p { margin: 0 0 12px; }
.gs-char-thumb { width: 112px; height: 112px; object-fit: contain; }
.gs-char-page-head { display: flex; align-items: center; gap: 12px; }
.gs-char-page-head h2 { margin: 0; font-size: 20px; }
.gs-char-hero { display: flex; gap: 16px; flex-wrap: wrap; }
.gs-char-stage { flex: none; width: min(100%, 220px); aspect-ratio: 1; margin: 0 auto; border-radius: 16px; display: grid; place-items: center; background: repeating-conic-gradient(#1a2040 0 25%, #141a36 0 50%) 0 0 / 20px 20px; }
.gs-sheet-preview--big { width: 200px; height: 200px; background-color: transparent; }
.gs-char-thumb--big { width: 200px; height: 200px; }
.gs-char-info { flex: 1; min-width: 220px; }
.gs-char-chat { padding: 0; overflow: hidden; }
.gs-chat--character { min-height: 380px; height: 52dvh; border-radius: 18px; }
.gs-btn--danger { background: #d9434b; border-color: #d9434b; color: #fff; }
.gs-linkbtn { border: 0; background: none; padding: 0; color: var(--accent); font: inherit; text-decoration: underline; cursor: pointer; }
.gs-hfkey { margin: 4px 0 8px; padding: 12px; border-radius: 12px; background: var(--surface); }
.gs-segment { display: flex; gap: 4px; padding: 4px; margin-bottom: 12px; border-radius: 12px; background: var(--surface); }
.gs-segment button { flex: 1; min-height: 40px; border: 0; border-radius: 9px; background: transparent; color: var(--muted); font: inherit; font-size: 14px; font-weight: 600; cursor: pointer; }
.gs-segment button[aria-checked="true"] { background: var(--bg); color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,.18); }
.gs-segment button:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.gs-import { display: flex; flex-direction: column; gap: 8px; margin-bottom: 10px; }
.gs-import .gs-btn { align-self: flex-start; }
.gs-import .gs-btn { position: relative; }
.gs-import .gs-btn:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
.gs-visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; opacity: 0; }
.gs-model-view { width: 100%; height: 100%; display: grid; place-items: center; touch-action: pan-y; }
.gs-model-view canvas { display: block; cursor: grab; }
.gs-chips--scroll { max-height: 132px; overflow-y: auto; }
.gs-card-head .gs-btn svg { color: currentColor; width: 18px; height: 18px; }
.gs-picker { flex: 1; min-width: 0; }
.gs-picker select { width: 100%; min-height: 44px; padding: 0 36px 0 12px; border-radius: 12px; border: 1px solid var(--border); background: var(--surface) url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='12' height='8'><path d='M1 1l5 5 5-5' stroke='%23999' stroke-width='2' fill='none'/></svg>") no-repeat right 12px center; color: var(--text); font: inherit; font-size: 16px; font-weight: 700; appearance: none; -webkit-appearance: none; text-overflow: ellipsis; }
.gs-picker select:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.gs-top { flex-wrap: nowrap; }
.gs-top .gs-new { margin-left: 0; }
.gs-btn--play { flex: 1; min-height: 48px; font-size: 16px; }
.gs-controls-hint { flex: 2; color: var(--muted); font-size: 12px; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.gs-more { position: relative; }
.gs-menu { position: absolute; right: 0; bottom: calc(100% + 6px); z-index: 30; min-width: 250px; padding: 6px; border-radius: 14px; background: var(--surface); border: 1px solid var(--border); box-shadow: 0 10px 30px rgba(0,0,0,.35); display: flex; flex-direction: column; }
.gs-menu button { display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 12px; border: 0; border-radius: 10px; background: transparent; color: var(--text); font: inherit; font-size: 14px; text-align: left; cursor: pointer; }
.gs-menu button:hover, .gs-menu button:focus-visible { background: var(--bg); outline: none; }
.gs-menu svg { width: 18px; height: 18px; color: var(--muted); }
.gs-menu-note { padding: 8px 12px; color: var(--muted); font-size: 13px; }
.gs-create { display: flex; flex-direction: column; gap: 8px; margin: 2px 0 14px; }
.gs-create textarea { width: 100%; min-height: 84px; padding: 12px 14px; border-radius: 14px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font: inherit; font-size: 16px; line-height: 1.4; resize: vertical; }
.gs-create textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
.gs-create-row { display: flex; align-items: center; gap: 8px; }
.gs-create-go { margin-left: auto; min-width: 120px; }
.gs-attach { position: relative; }
.gs-attach:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
.gs-asset--sound-tile .gs-sound-play { width: 48px; height: 48px; border-radius: 50%; border: 0; background: color-mix(in srgb, var(--accent) 20%, var(--surface)); color: var(--text); display: grid; place-items: center; cursor: pointer; }
.gs-sound-play svg { width: 22px; height: 22px; }
.gs-sound-play[aria-pressed="true"] { background: var(--accent); color: var(--accent-contrast, #fff); }
.gs-sound-play:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.gs-credit { display: block; margin-top: 2px; color: var(--muted); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.gs-more-tools { margin-top: 4px; }
.gs-use { min-height: 36px; padding: 0 12px; }
.gs-asset-actions { align-items: center; gap: 2px; }
.gs-more-tools > summary { min-height: 44px; display: flex; align-items: center; padding: 0 16px; border-radius: 14px; background: var(--surface); color: var(--muted); font-weight: 600; cursor: pointer; list-style: none; }
.gs-more-tools > summary::-webkit-details-marker { display: none; }
.gs-more-tools > summary::after { content: '▾'; margin-left: auto; }
.gs-more-tools[open] > summary::after { content: '▴'; }
.gs-more-tools > .gs-card { margin-top: 12px; }
@media (prefers-reduced-motion: no-preference) {
  .gs-game-chip, .gs-tab, .gs-chip, .gs-btn { transition: background-color .15s ease, color .15s ease, transform .1s ease; }
  .gs-btn:active, .gs-chip:active { transform: scale(.97); }
}
`

const store = () => window.mobius?.storage
const readEngineFile = (path) => store().getText(path)

// Every game is also its own Möbius app. publish_game.py (run by an agent,
// since installing an app is an agent tool) packs and installs it, then
// records published/<gameId>.json with the fingerprint of the game file it
// installed. The studio agent publishes at the end of each change; for changes
// made without it (a new template game, a version restore) the studio starts a
// small hidden publish turn on the light background model.
const STUDIO_DIR = '/data/apps/game-studio'

// Godot games share one engine (stored once under engine/ by godot_build.py setup).
const GODOT_VERSION = '4.7.2'
let godotEnginePromise = null
function godotEngineFiles() {
  godotEnginePromise ||= Promise.all([
    store().getBlob(`engine/godot-${GODOT_VERSION}.wasm.gz`),
    store().getText(`engine/godot-${GODOT_VERSION}.js`),
  ]).then(([wasmGz, js]) => {
    if (!wasmGz || !js) throw new Error('The Godot engine is not installed in the studio yet.')
    return { wasmGz, js }
  }).catch((err) => { godotEnginePromise = null; throw err })
  return godotEnginePromise
}
const isHiddenGame = (id) => String(id || '').startsWith('_')

// A project guest (editor or maintainer) runs the studio from the shared
// project page with a studio pass: storage then holds only that project's game,
// the art it uses and the guest's own scratch, and agent jobs go to the guest's
// own assistant. Owner-only tools (publishing, sharing, starters) stay hidden.
function isGuestPass(token) {
  try {
    const part = String(token || '').split('.')[1] || ''
    const claims = JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/').padEnd(Math.ceil(part.length / 4) * 4, '=')))
    return claims?.scope === 'guest_app'
  } catch { return false }
}

// First steps for an empty scene: small, concrete, one layer at a time.
const SCENE_SUGGESTIONS = [
  ['Flat grassy field', 'Make a flat grassy terrain.'],
  ['Rolling hills', 'Make rolling green hills with a small lake.'],
  ['Sunset sky', 'Give the scene a warm sunset sky with soft fog.'],
]

const SUGGESTIONS = [
  ['3D platformer', 'I want a 3D platformer with floating islands to jump across.'],
  ['Survivor roguelike', 'I want a survivor roguelike like Vampire Survivors: enemies swarm me, I fight with combos, collect XP, pick upgrades, new items and moves, then face mini bosses and a final boss. Use my characters.'],
  ['Forest adventure', 'I want a 3D forest I can explore, with things to collect.'],
  ['Kart racing', 'I want a 3D kart racing game on a colourful track.'],
  ['Space shooter', 'I want a 3D space shooter with a boss at the end.'],
]

function newGameId() {
  return 'g-' + Math.random().toString(36).slice(2, 8)
}

function hashText(text) {
  let h = 2166136261
  for (let i = 0; i < text.length; i += 1) h = Math.imul(h ^ text.charCodeAt(i), 16777619)
  return (h >>> 0).toString(36)
}

// Inside a Game project the studio shows that project's one game. Its game is
// the one whose link (projects/<gameId>.json) names the project; a new project
// gets a game whose id comes from the project's, so a reload never adds a second.
async function gameForProject(projectId) {
  const { entries } = await store().listWithStatus('projects/', { includeContent: true })
  const linked = entries.find((e) => e.type === 'file' && e.name.endsWith('.json') && e.content?.projectId === projectId)
  return linked ? linked.name.slice(0, -5) : null
}

async function loadGames() {
  // listWithStatus asks the server when online; list() may answer from this
  // device's cache and miss games made on another device.
  const { entries } = await store().listWithStatus('games/', { includeContent: true })
  return entries
    .filter((e) => e.type === 'file' && /^[a-z0-9-]+\.json$/i.test(e.name) && !/\.(error|saves)\.json$/.test(e.name) && e.content?.id)
    .map((e) => e.content)
    .sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')))
}

async function addModel(assets, name, blob, info) {
  await store().setBlob(`models/${name}.glb`, blob, { contentType: 'model/gltf-binary' })
  const latest = (await store().get('assets.json')) || assets
  const next = { sprites: {}, sounds: {}, ...latest, models: { ...(latest.models || {}), [name]: { ...info, size: blob.size } } }
  await store().set('assets.json', next)
  return next
}

// Keeps one version per distinct game file so any change can be undone.
async function recordVersion(gameId, html) {
  if (!html) return null
  const path = `versions/${gameId}.json`
  const list = (await store().get(path)) || []
  const hash = hashText(html)
  if (list[0]?.hash === hash) return list
  const at = new Date().toISOString()
  const file = `versions/${gameId}/${at.replace(/[:.]/g, '-')}.html`
  await store().setText(file, html, { contentType: 'text/html' })
  const next = [{ at, hash, file }, ...list].slice(0, 30)
  await store().set(path, next)
  return next
}

function useWide() {
  const query = '(min-width: 960px)'
  const [wide, setWide] = useState(() => window.matchMedia?.(query).matches ?? false)
  useEffect(() => {
    const media = window.matchMedia?.(query)
    if (!media) return undefined
    const update = () => setWide(media.matches)
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return wide
}

function StudioChat({ appId, game, onTurnDone, onSent }) {
  const mountRef = useRef(null)
  const turnDoneRef = useRef(onTurnDone)
  turnDoneRef.current = onTurnDone
  const sentRef = useRef(onSent)
  sentRef.current = onSent
  const [error, setError] = useState('')
  useEffect(() => {
    const mount = mountRef.current
    if (!mount || !window.mobius?.chat) return undefined
    let handle
    let disposed = false
    setError('')
    modelFor('creative').then((pick) => window.mobius.chat({
      ...pick,
      mount,
      persist: `chats/${game.id}.json`,
      systemPrompt: studioAgentPrompt({ appId, game }),
      picker: false,
      guidance: game.kind === 'godot'
        ? 'Build it step by step, in any look you like: "make a street with a road and pavement", "add a ramen shop on the left", "add my hero as the player", "make it sunset". Each message does just that.'
        : game.kind === 'scene'
        ? 'Build it step by step: "make a flat grassy terrain", "add my cowboy as the player", "put five coins around", "make the sky a sunset". Each message does just that.'
        : 'Describe your game, like "I want a 2D platformer" or "a 3D forest". Then keep shaping it: "add a meadowy platform to jump on", "use my pink-cat as the hero".',
      onMessageSent: () => sentRef.current?.(),
      onTurnDone: () => turnDoneRef.current?.(),
    })).then((h) => { if (disposed) h.destroy(); else handle = h })
      .catch((err) => setError(err?.message || 'The studio agent could not start.'))
    return () => { disposed = true; handle?.destroy() }
  }, [appId, game.id])
  return (
    <>
      {error && <p className="gs-error" role="alert">{error}</p>}
      <div className="gs-chat" ref={mountRef} />
    </>
  )
}

// "Build together": a game's Project is where friends join, play and edit it.
// Invitations, roles, who's online and who's editing which file all live there.
// Share to play: one public link where anyone plays a fresh copy of the game,
// never the owner's progress, chats or files (share_game.py makes the link).
function SharePlaySheet({ gameName, playUrl, busy, error, onShare, onStop, onClose }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onClose])
  const copy = async () => {
    const ok = await window.mobius?.clipboard?.writeText?.(playUrl).catch(() => false)
    setCopied(!!ok)
  }
  return (
    <div className="gs-sheet-scrim" onClick={onClose}>
      <section className="gs-sheet" role="dialog" aria-modal="true" aria-labelledby="gs-share-title" onClick={(event) => event.stopPropagation()}>
        <div className="gs-sheet-head">
          <h2 id="gs-share-title">Share {gameName || 'this game'} to play</h2>
          <button type="button" className="gs-icon-btn" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></button>
        </div>
        <p className="gs-sheet-lead">Anyone with the link plays a fresh game, starting from the beginning. They don't need an account and never see your progress, chats or files. Their progress lasts while their page is open.</p>
        {playUrl ? (
          <div className="gs-share-link">
            <input readOnly value={playUrl} aria-label="Play link" onFocus={(event) => event.target.select()} />
            <button type="button" className="gs-btn gs-btn--primary" onClick={copy}>{copied ? 'Copied' : 'Copy link'}</button>
          </div>
        ) : (
          <p className="gs-sheet-lead" role="status">{busy ? 'Making the link: publishing the latest version of your game…' : 'No link yet.'}</p>
        )}
        {error && <p className="gs-error" role="alert">{error}</p>}
        <div className="gs-sheet-actions">
          {playUrl && <button type="button" className="gs-btn" disabled={busy} onClick={onStop}>{busy ? 'Working…' : 'Stop sharing'}</button>}
          {!playUrl && <button type="button" className="gs-btn gs-btn--primary" disabled={busy} onClick={onShare}>{busy ? 'Making the link…' : 'Make a play link'}</button>}
          <button type="button" className="gs-btn" onClick={onClose}>Close</button>
        </div>
      </section>
    </div>
  )
}

function BuildTogetherSheet({ gameName, onOpen, onClose }) {
  useEffect(() => {
    const onKey = (event) => { if (event.key === 'Escape') onClose() }
    addEventListener('keydown', onKey)
    return () => removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="gs-sheet-scrim" onClick={onClose}>
      <section className="gs-sheet" role="dialog" aria-modal="true" aria-labelledby="gs-together-title" onClick={(event) => event.stopPropagation()}>
        <div className="gs-sheet-head">
          <h2 id="gs-together-title">Build {gameName || 'this game'} together</h2>
          <button type="button" className="gs-icon-btn" aria-label="Close" onClick={onClose}><X aria-hidden="true" /></button>
        </div>
        <p className="gs-sheet-lead">Every game has a project: its files and their full history. Friends you invite there can play it and change it with you.</p>
        <ol className="gs-together-steps">
          <li><div><b>Invite</b><span>In the project, tap Share, then Work together. Editors can change the game; viewers can watch and play. Each link works once.</span></div></li>
          <li><div><b>Play the latest</b><span>Anyone in the project taps Build on Play to try the game as it is right now, art and all.</span></div></li>
          <li><div><b>Take a part each</b><span>Opening a file shows everyone you're on it, and Activity shows each change and who made it. Split the work: levels, player, enemies, sound.</span></div></li>
          <li><div><b>Ask the AI through you</b><span>The game's AI stays here with you. Friends write wishes in requests.md; you see them under More, then Wishes, and hand them to the AI.</span></div></li>
          <li><div><b>Share a playtest link</b><span>Anyone can play without an account: find the game's own app in the side menu, tap its ⋯ button, choose Share app and turn on public use. Players tap Note to tell you what they think; notes arrive under Wishes.</span></div></li>
        </ol>
        <div className="gs-sheet-actions">
          <button type="button" className="gs-btn" onClick={onClose}>Close</button>
          <button type="button" className="gs-btn gs-btn--primary" onClick={onOpen}><Group aria-hidden="true" />Open the project</button>
        </div>
      </section>
    </div>
  )
}

export default function App({ appId, token }) {
  setModelToken(token)
  const [games, setGames] = useState([])
  const [confirmDelete, setConfirmDelete] = useState(null)
  // Godot games work like the old scene builder: Edit shows the world frozen with a free camera
  // (tap to select, see inside, home, object list, add, undo); Play runs the game in the panel.
  const godotViewRef = useRef(true)
  const [godotPlay, setGodotPlay] = useState(false)
  const [godotObjects, setGodotObjects] = useState([])
  const [godotSelected, setGodotSelected] = useState(null)
  const [godotCut, setGodotCut] = useState(null)
  const [godotSheet, setGodotSheet] = useState(null)
  const [godotUndoing, setGodotUndoing] = useState(false)
  const godotCamRef = useRef({})
  const godotStateRef = useRef({})
  const [currentId, setCurrentId] = useState(null)
  const [html, setHtml] = useState(null)
  const htmlRef = useRef(null)
  htmlRef.current = html
  const [assets, setAssets] = useState({ sprites: {}, sounds: {} })
  const [tab, setTab] = useState('studio')
  const [chatKey, setChatKey] = useState(0)
  const [useRequest, setUseRequest] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [gameError, setGameError] = useState(null)
  const [versions, setVersions] = useState([])
  const [showVersions, setShowVersions] = useState(false)
  const [showTogether, setShowTogether] = useState(false)
  const [showShare, setShowShare] = useState(false)
  const [shareBusy, setShareBusy] = useState(false)
  const [shareError, setShareError] = useState('')
  const [showWishes, setShowWishes] = useState(false)
  const [focus, setFocus] = useState(false)
  godotViewRef.current = !focus && !godotPlay
  const [loadError, setLoadError] = useState('')
  const [gamesLoaded, setGamesLoaded] = useState(false)
  const [published, setPublished] = useState(null)
  const [project, setProject] = useState(null)
  // Set when the studio runs inside a Game project (shell intent project:<id>).
  const [hostProjectId, setHostProjectId] = useState(null)
  const [hostGameId, setHostGameId] = useState(null)
  // The project shows the Scene/Characters/Assets choice beside its files.
  const [hostTabs, setHostTabs] = useState(false)
  // Bumped by the project page when the guest's assistant finishes a turn.
  const [hostRefresh, setHostRefresh] = useState(0)
  const guest = useMemo(() => isGuestPass(token), [token])
  const guestRef = useRef(guest)
  guestRef.current = guest
  const reloadAssetsRef = useRef(null)
  const hostProjectRef = useRef(null)
  hostProjectRef.current = hostProjectId
  const [publishing, setPublishing] = useState(false)
  const [turnSignal, setTurnSignal] = useState(0)
  const agentBusyRef = useRef(false)
  const [agentBusy, setAgentBusy] = useState(false)
  const markBusy = (value) => { agentBusyRef.current = value; setAgentBusy(value) }
  const publishAskedRef = useRef(new Set())
  const autoCreatedRef = useRef(false)
  const createBlankGameRef = useRef(null)
  const frameRef = useRef(null)
  const savesRef = useRef({})
  const motionRef = useRef(null)
  const voiceRef = useRef(null)
  voiceRef.current ||= createVoice()
  const [voiceMode, setVoiceMode] = useState('browser')
  useEffect(() => {
    store().get('settings.json').then((s) => { if (s?.voiceMode) { setVoiceMode(s.voiceMode); voiceRef.current.setMode(s.voiceMode) } }).catch(() => {})
  }, [])
  const changeVoiceMode = (mode) => {
    setVoiceMode(mode)
    voiceRef.current.setMode(mode)
    store().set('settings.json', { voiceMode: mode }).catch(() => {})
  }

  const game = games.find((g) => g.id === currentId) || null
  // switching between the preview and the full-screen game restarts a Godot game in that mode
  const isGodot = game?.kind === 'godot'
  const [startInfo, setStartInfo] = useState(null)
  const [clock, setClock] = useState(() => Date.now())
  useEffect(() => {
    setStartInfo(null)
    if (!currentId || !isGodot) return undefined
    let alive = true
    store().get(`games/${currentId}.start.json`).then((v) => alive && setStartInfo(v || null)).catch(() => {})
    const off = store().subscribe(`games/${currentId}.start.json`, (v) => alive && setStartInfo(v || null))
    return () => { alive = false; off?.() }
  }, [currentId, isGodot])
  const startPending = html === '' && ['queued', 'engine', 'building'].includes(startInfo?.state)
  // The server writes the start file, and storage subscriptions only hear this
  // window's own writes: read the server's copy every few seconds until it settles.
  useEffect(() => {
    if (!startPending) return undefined
    const id = currentId
    const timer = setInterval(async () => {
      setClock(Date.now())
      const fresh = await store().getWithVersion(`games/${id}.start.json`).catch(() => null)
      if (!fresh?.value) return
      setStartInfo(fresh.value)
      if (fresh.value.state !== 'done') return
      const built = await store().getWithVersion(`games/${id}.html`, 'text').catch(() => null)
      if (typeof built?.value === 'string' && built.value) {
        setHtml(built.value)
        setReloadKey((k) => k + 1)
      }
    }, 4000)
    return () => clearInterval(timer)
  }, [startPending, currentId])
  // No word from the helper for a while (it never ran, or stopped mid-way) counts as failed.
  const startStalled = startPending && clock - Date.parse(startInfo.at || 0) > (startInfo.state === 'queued' ? 3 : 8) * 60000
  const startFailed = html === '' && (startInfo?.state === 'failed' || startStalled)
  useEffect(() => { if (isGodot) setReloadKey((k) => k + 1) }, [focus, godotPlay])
  useEffect(() => { setGodotPlay(false); setGodotObjects([]); setGodotSelected(null); setGodotCut(null); setGodotSheet(null) }, [currentId])
  godotStateRef.current = { selected: godotSelected, cut: godotCut }
  useEffect(() => { setGodotUndoing(false) }, [html])
  const board = useRequestBoard(currentId)
  const notes = usePlaytestNotes(currentId)
  const wishes = { fresh: board.fresh + notes.fresh }
  const wide = useWide()
  // A game only runs while it is on screen: a hidden (zero-size) frame breaks
  // WebGL start-up, and a background game would keep playing sound.
  const playVisible = tab === 'studio'

  const refreshGames = useCallback(async () => {
    const list = await loadGames()
    setGames(list)
    setCurrentId((id) => (id && list.some((g) => g.id === id) ? id : list[0]?.id ?? null))
    setGamesLoaded(true)
    if (!list.length && !autoCreatedRef.current && !hostProjectRef.current) {
      autoCreatedRef.current = true
      createBlankGameRef.current?.()
    }
    return list
  }, [token])

  useEffect(() => {
    refreshGames().catch(() => setLoadError('Your games could not load. Check your connection and reopen the studio.'))
    store().get('assets.json').then((value) => value && setAssets({ sprites: {}, sounds: {}, ...value })).catch(() => {})
    return store().subscribe('assets.json', (value) => value && setAssets({ sprites: {}, sounds: {}, ...value }))
  }, [refreshGames])

  // Games can be made on another device or by the agent in another chat, so
  // pick up new ones when the studio comes back into view and while it is open.
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') refreshGames().catch(() => {}) }
    document.addEventListener('visibilitychange', refresh)
    window.addEventListener('focus', refresh)
    const timer = setInterval(refresh, 30000)
    return () => {
      document.removeEventListener('visibilitychange', refresh)
      window.removeEventListener('focus', refresh)
      clearInterval(timer)
    }
  }, [refreshGames])

  // Load the current game's code, saves, and versions; follow agent edits live.
  useEffect(() => {
    if (!currentId) return undefined
    let alive = true
    setHtml(null)
    setGameError(null)
    setShowVersions(false)
    savesRef.current = {}
    store().get(`games/${currentId}.saves.json`).then((s) => { if (alive && s) savesRef.current = s }).catch(() => {})
    store().get(`versions/${currentId}.json`).then((v) => alive && setVersions(v || [])).catch(() => {})
    store().getText(`games/${currentId}.html`).then((text) => {
      if (!alive) return
      setHtml(text || '')
    }).catch(() => alive && setHtml(''))
    const off = store().subscribeText(`games/${currentId}.html`, (text) => { if (alive && typeof text === 'string') setHtml(text) })
    return () => { alive = false; off?.() }
  }, [currentId])

  // After an agent turn, read the server's copy: the cached read can still
  // hold the previous game for a moment.
  const onTurnDone = useCallback(async () => {
    markBusy(false)
    setTurnSignal((n) => n + 1)
    await refreshGames().catch(() => {})
    const fresh = await store().getWithVersion(`games/${currentId}.html`, 'text').catch(() => null)
    if (typeof fresh?.value === 'string') {
      setHtml(fresh.value)
      setGameError(null)
      setReloadKey((k) => k + 1)
      ensurePublished(currentId, fresh.value)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId, refreshGames])

  // A guest's assistant finished a turn: read what it changed.
  const onTurnDoneRef = useRef(onTurnDone)
  onTurnDoneRef.current = onTurnDone
  useEffect(() => {
    if (!hostRefresh) return
    onTurnDoneRef.current?.()
    reloadAssetsRef.current?.()
  }, [hostRefresh])

  // Which Möbius app this game is, kept current as publishes land.
  useEffect(() => {
    if (!currentId) return undefined
    let alive = true
    setPublished(null)
    setPublishing(false)
    const path = `published/${currentId}.json`
    store().getWithVersion(path).then((r) => alive && setPublished(r?.value || null)).catch(() => {})
    const off = store().subscribe(path, (value) => { if (alive) setPublished(value || null) })
    return () => { alive = false; off?.() }
  }, [currentId])

  // The game's Project (its home: the files and their history), once it has one.
  useEffect(() => {
    if (!currentId) return undefined
    let alive = true
    setProject(null)
    const path = `projects/${currentId}.json`
    store().getWithVersion(path).then((r) => alive && setProject(r?.value || null)).catch(() => {})
    const off = store().subscribe(path, (value) => { if (alive) setProject(value || null) })
    return () => { alive = false; off?.() }
  }, [currentId])
  const openProject = () => project?.projectId && window.mobius?.projects?.open(project.projectId).catch(() => {})

  // Install or update the game's own app when its file differs from the one
  // last installed, unless the studio agent is mid-turn (it publishes itself).
  async function ensurePublished(gameId, text, force = false) {
    if (guestRef.current || !gameId || !text || isHiddenGame(gameId) || (agentBusyRef.current && !force) || !window.mobius?.chat?.start) return
    // A game deleted while its code is still on screen must not be reinstalled.
    const meta = await store().getWithVersion(`games/${gameId}.json`).then((r) => r?.value).catch(() => null)
    if (!meta?.id) return
    // Scene games become an app only when the person asks (More → Install as its own app).
    if (meta.kind === 'scene' && !force) return
    // Godot games play inside the studio only for now: the publish tools don't package them yet.
    if (meta.kind === 'godot') return
    const hash = hashText(text)
    const record = await store().getWithVersion(`published/${gameId}.json`).then((r) => r?.value).catch(() => undefined)
    if (record === undefined || record?.hash === hash) return
    const key = `${gameId}:${hash}`
    if (publishAskedRef.current.has(key)) return
    publishAskedRef.current.add(key)
    const name = games.find((g) => g.id === gameId)?.name || 'this game'
    if (gameId === currentId) {
      setPublishing(true)
      setTimeout(() => setPublishing(false), 4 * 60 * 1000)
    }
    try {
      await window.mobius.chat.start({
        scope: `publish:${key}`,
        ownerVisible: false,
        title: `Install ${name} as an app`,
        ...(await modelFor('quick')),
        systemPrompt: 'You install Game Studio games as Möbius apps. Run the one command you are given with the Bash tool, then reply in one short sentence saying whether it worked. If it fails, say why in plain words. Do nothing else.',
        draft: `Run: python3 ${STUDIO_DIR}/publish_game.py ${appId} ${gameId}`,
      })
    } catch {
      publishAskedRef.current.delete(key)
      if (gameId === currentId) setPublishing(false)
    }
  }

  useEffect(() => {
    if (!published || !html) return
    if (published.hash === hashText(html)) setPublishing(false)
  }, [published, html])

  // Changes that did not come from an agent turn (a new template game, a
  // restored version, a game made before apps existed) publish shortly after.
  useEffect(() => {
    if (!currentId || !html) return undefined
    const timer = setTimeout(() => ensurePublished(currentId, html), 2500)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentId, html])

  // Leaving Game Studio (the shell keeps it loaded, hidden) silences and freezes the game.
  const visibilityRef = useRef(null)
  useEffect(() => {
    const relay = relayVisibility(() => frameRef.current, (visible) => { if (!visible) voiceRef.current?.stop() })
    visibilityRef.current = relay
    return relay.stop
  }, [])

  // When the project lists the tabs, tell it when the studio switches on its
  // own (e.g. "Use in game" jumps to the scene), so its list stays in step.
  useEffect(() => {
    if (!hostTabs || !tab) return
    window.parent.postMessage({ type: 'moebius:host-section', section: tab }, '*')
  }, [hostTabs, tab])

  // A game's own app opens the studio on that game from its Edit button.
  useEffect(() => {
    const onIntent = (event) => {
      if (event.source !== window.parent || event.data?.type !== 'moebius:app-intent') return
      // project:<id> runs the studio inside that project; project:<id>:<tab>
      // also means the project lists the tabs itself and picks this one.
      // project:<id>[:<tab>][#<n>]: #<n> changes when the guest's assistant
      // finished a turn, so the studio reads the files it changed.
      const hosted = /^project:([A-Za-z0-9-]+)(?::(studio|characters|assets))?(?:#(\d+))?$/.exec(String(event.data.intent || ''))
      if (hosted) {
        setHostProjectId(hosted[1])
        setHostTabs(!!hosted[2])
        if (hosted[2]) setTab(hosted[2])
        else setTab((current) => current || 'studio')
        if (hosted[3]) setHostRefresh(Number(hosted[3]))
        return
      }
      const match = /^game:([A-Za-z0-9_-]+)$/.exec(String(event.data.intent || ''))
      if (!match) return
      setCurrentId(match[1])
      setTab('studio')
    }
    window.addEventListener('message', onIntent)
    return () => window.removeEventListener('message', onIntent)
  }, [])
  const openApp = () => published?.appId && window.parent.postMessage({ type: 'moebius:open-app', appId: published.appId }, '*')

  // Every distinct game file becomes a version, however it arrived (agent
  // turn, live update, or a restore).
  useEffect(() => {
    if (!currentId || !html) return undefined
    let alive = true
    recordVersion(currentId, html).then((v) => alive && v && setVersions(v)).catch(() => {})
    return () => { alive = false }
  }, [currentId, html])

  // 3D models are handed to games as bytes; wait for them so a game never
  // starts with its fallback when the real model is on its way.
  // Each name carries its last change, so an edited model reloads into games.
  // Only the models a game names are packed (as publish_game.used_models does): packing
  // the whole library (tens of MB, now about 90 MB as text) crashes phones, and took
  // Möbius down on iPhone in a reload loop. Scene games name theirs in the scene data
  // ("asset" / "character"), so a model added in the editor loads as soon as it is placed.
  const usesModel = (name) => !!html && (html.includes('studio.models(')
    || ['"', "'", '`'].some((q) => html.includes(q + name + q)))
  const modelKey = Object.keys(assets.models || {}).filter(usesModel).sort()
    .map((name) => `${name}:${assets.characters?.[name]?.updatedAt || ''}${assets.models[name]?.size || ''}`).join(',')
  const [modelData, setModelData] = useState({ key: null, data: {} })
  useEffect(() => {
    let alive = true
    const names = modelKey ? modelKey.split(',').map((entry) => entry.split(':')[0]) : []
    Promise.all(names.map(async (name) => {
      const blob = await readModel(`models/${name}.glb`)
      return [name, blob ? await blobToBase64(blob) : null]
    })).then((pairs) => {
      if (alive) setModelData({ key: modelKey, data: Object.fromEntries(pairs.filter(([, b64]) => b64)) })
    })
    return () => { alive = false }
  }, [modelKey])

  // Sound files from the Assets tab, loaded the same way (keyed by their last change).
  const soundKey = audioKey(assets)
  const [audioData, setAudioData] = useState({ key: null, data: {} })
  useEffect(() => {
    let alive = true
    const names = soundKey ? soundKey.split(',').map((entry) => entry.split(':')[0]) : []
    Promise.all(names.map(async (name) => {
      const blob = await readModel(`audio/${name}.mp3`)
      return [name, blob ? await blobToBase64(blob) : null]
    })).then((pairs) => {
      if (alive) setAudioData({ key: soundKey, data: Object.fromEntries(pairs.filter(([, b64]) => b64)) })
    })
    return () => { alive = false }
  }, [soundKey])
  const library = useMemo(() => withAudio(assets, audioData.data), [assets, audioData])

  // The game's art: its style's kit (shared) plus pictures added to this game.
  const artId = game?.art || null
  const [art, setArt] = useState({ key: null, value: null })
  useEffect(() => {
    if (!currentId) return undefined
    let alive = true
    const key = `${currentId}|${artId}|${reloadKey}`
    const load = async () => {
      const [kit, own] = await Promise.all([
        artId ? store().get(`art/${artId}.json`).catch(() => null) : null,
        store().get(`games/${currentId}.art.json`).catch(() => null),
      ])
      if (alive) setArt({ key, value: mergeArt(kit, own), missing: Boolean(artId && !kit) })
    }
    load()
    const off = store().subscribe(`games/${currentId}.art.json`, () => { if (alive) load() })
    return () => { alive = false; off?.() }
  }, [currentId, artId, reloadKey])
  const artReady = art.key === `${currentId}|${artId}|${reloadKey}`

  const gameEngine = useEngine(html, readEngineFile)
  const srcDoc = useMemo(() => (html && gameEngine.ready && modelData.key === modelKey && audioData.key === soundKey && artReady
    ? buildGameDocument(html, { sprites: assets.sprites, sounds: assets.sounds, models: modelData.data, art: withLibrary(art.value, library), saves: savesRef.current, engine: gameEngine.engine })
    : null),
    // Saves are read at build time on purpose: a save must not reload the game.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [html, gameEngine, assets.sprites, assets.sounds, assets.characters, modelData, modelKey, audioData, soundKey, art, artReady, reloadKey])

  const modelActions = {
    catalog: MODEL_CATALOG,
    async addCatalog(entry) {
      setAssets(await addModel(assets, entry.name, await fetchCatalogModel(entry, token), { title: entry.title, credit: entry.credit }))
    },
    async upload(file, name) {
      setAssets(await addModel(assets, name, checkModelFile(file), { title: name, credit: 'Your model' }))
    },
    async remove(name) {
      const latest = (await store().get('assets.json')) || assets
      const models = { ...(latest.models || {}) }
      delete models[name]
      const next = { ...latest, models }
      await store().set('assets.json', next)
      await store().remove(`models/${name}.glb`).catch(() => {})
      setAssets(next)
    },
  }

  // Messages from the running game: errors, saves, and tilt requests.
  useEffect(() => {
    const onMessage = (event) => {
      if (!frameRef.current || event.source !== frameRef.current.contentWindow) return
      const msg = event.data || {}
      if (msg.type === 'godot:objects') {
        setGodotObjects(Array.isArray(msg.list) ? msg.list.map(String) : [])
      } else if (msg.type === 'godot:selected') {
        const name = msg.name ? String(msg.name) : null
        setGodotSelected(name)
        // the assistant reads this when the person says "this" or "the selected one"
        store().set(`games/${currentId}.selected.json`, { name, at: new Date().toISOString() }).catch(() => {})
      } else if (msg.type === 'godot:camera') {
        godotCamRef.current = { ...godotCamRef.current, [currentId]: msg.camera }
      } else if (msg.type === 'godot:ready') {
        // A Godot game's sandboxed page cannot read storage itself: hand it the
        // shared engine and this game's pack as blobs (cheap to post).
        const target = event.source
        Promise.all([
          godotEngineFiles(),
          // each build has its own file (devices keep a stored binary forever once read)
          store().getBlob((/<meta name="studio-pck" content="([^"]+)"/.exec(htmlRef.current || '') || [])[1] || `games/${currentId}.pck`),
        ]).then(([engine, pck]) => {
          target.postMessage({ type: 'godot:files', mode: godotViewRef.current ? 'view' : 'play', camera: godotCamRef.current[currentId] || null, selected: godotStateRef.current.selected, cut: godotStateRef.current.cut, wasmGz: engine.wasmGz, engineJs: engine.js, pck, assetBase: new URL(`/app-assets/by-id/${appId}/`, window.location.href).href }, '*')
        }).catch((err) => {
          const info = { message: 'This Godot game could not load its files. Ask the assistant to rebuild it.', detail: String(err?.message || err), at: new Date().toISOString() }
          setGameError(info)
        })
      } else if (msg.type === 'studio:error') {
        const info = { message: String(msg.message || 'Unknown error'), detail: String(msg.detail || ''), at: new Date().toISOString() }
        setGameError(info)
        store().set(`games/${currentId}.error.json`, info).catch(() => {})
      } else if (msg.type === 'studio:save' && typeof msg.key === 'string') {
        savesRef.current = { ...savesRef.current, [msg.key]: msg.value }
        store().set(`games/${currentId}.saves.json`, savesRef.current).catch(() => {})
      } else if (msg.type === 'studio:public-read') {
        frameRef.current?.contentWindow?.postMessage({ type: 'studio:public-result', id: msg.id, value: null, visitor: false }, '*')
      } else if (msg.type === 'studio:tilt-start') {
        startTilt()
      } else if (msg.type === 'studio:say') {
        const reply = (error) => frameRef.current?.contentWindow?.postMessage({ type: 'studio:say-done', id: msg.id, error }, '*')
        voiceRef.current.say(msg.text, { voice: msg.voice, pitch: msg.pitch, rate: msg.rate, lang: msg.lang })
          .then(() => reply(), (err) => reply(String(err?.message || err)))
      } else if (msg.type === 'studio:say-stop') {
        voiceRef.current.stop()
      }
    }
    window.addEventListener('message', onMessage)
    return () => window.removeEventListener('message', onMessage)
  }, [currentId])

  function startTilt() {
    const caps = window.mobius?.capabilities
    if (motionRef.current || !caps?.available?.('device.motion', 1)) return
    const session = caps.open('device.motion', { rateHz: 30 })
    motionRef.current = session
    session.on('sample', ({ orientation, screenAngle }) => {
      if (!orientation || orientation.gamma == null) return
      let x = orientation.gamma / 35
      let y = (orientation.beta - 40) / 35
      if (screenAngle === 90) [x, y] = [y, -x]
      else if (screenAngle === 270 || screenAngle === -90) [x, y] = [-y, x]
      frameRef.current?.contentWindow?.postMessage({ type: 'studio:tilt', x, y }, '*')
    })
    const clear = () => { motionRef.current = null }
    session.ready?.catch(clear)
    session.result?.then(clear, clear)
  }
  useEffect(() => () => { motionRef.current?.finish?.(); motionRef.current = null; voiceRef.current?.stop() }, [currentId, reloadKey, playVisible])

  // Agents save assets and publish records on the server; while one is in
  // flight, read the server's copy so the studio shows the result without a reload.
  const reloadAssets = useCallback(() => store().getWithVersion('assets.json')
    .then((r) => { if (r?.value) setAssets({ sprites: {}, sounds: {}, ...r.value }) }).catch(() => {}), [])
  useEffect(() => {
    if (!publishing || !currentId) return undefined
    const timer = setInterval(() => {
      store().getWithVersion(`published/${currentId}.json`).then((r) => { if (r?.value) setPublished(r.value) }).catch(() => {})
    }, 5000)
    return () => clearInterval(timer)
  }, [publishing, currentId])

  // Read-modify-write against the server copy: agents also write assets.json.
  const updateAssets = async (change) => {
    const next = await updateShared('assets.json', (latest) => change({ sprites: {}, sounds: {}, characters: {}, ...(latest || assets) }), assets)
    setAssets(next)
  }

  // The Assets tab hands over a whole new copy; apply only what it changed onto the
  // server's latest, so a character or asset the AI saved meanwhile is kept.
  const saveAssets = (next) => {
    const before = assets
    setAssets(next)
    updateAssets((latest) => {
      const out = { ...latest }
      for (const group of new Set([...Object.keys(before), ...Object.keys(next)])) {
        const was = before[group]
        const now = next[group]
        if (was === now) continue
        if (now && was && typeof now === 'object' && typeof was === 'object' && !Array.isArray(now)) {
          const merged = { ...(latest[group] || {}) }
          for (const key of new Set([...Object.keys(was), ...Object.keys(now)])) {
            if (!(key in now)) delete merged[key]
            else if (was[key] !== now[key]) merged[key] = now[key]
          }
          out[group] = merged
        } else out[group] = now
      }
      return out
    }).catch(() => setLoadError('That asset could not be saved. Try again.'))
  }

  const [creating, setCreating] = useState(false)
  // A genre game starts as its playable template; a blank idea starts empty
  // and goes straight to the agent.
  // The first build of a new Godot game runs on the server in a small hidden turn
  // (godot_build.py new). It reports to games/<id>.start.json: queued (written here),
  // engine (the one-time Godot download, with pct), building, done or failed.
  const startGodotGame = async ({ id, name }, retry = false) => {
    await store().set(`games/${id}.start.json`, { state: 'queued', at: new Date().toISOString() })
    if (!window.mobius?.chat?.start) return
    window.mobius.chat.start({
      scope: retry ? `godot-new:${id}:${Date.now()}` : `godot-new:${id}`,
      ownerVisible: false,
      title: `Start ${name}`,
      ...(await modelFor('quick')),
      systemPrompt: 'You start new Game Studio games. Run the one command you are given in the shell, with a 10-minute timeout (the first game downloads the game engine). Then reply in one short sentence saying whether it worked. If it fails, say why in plain words. Do nothing else.',
      draft: `Run: python3 ${STUDIO_DIR}/godot_build.py new ${appId} ${id} ${JSON.stringify(name)}`,
    }).catch(() => store().set(`games/${id}.start.json`, { state: 'failed', at: new Date().toISOString(), message: 'The studio could not start its helper.' }).catch(() => {}))
  }

  // A game starts as an empty canvas; the person describes it in the chat.
  const createBlankGame = async ({ id = newGameId(), name = 'Untitled game' } = {}) => {
    setCreating(true)
    try {
      // New games are Godot games: the build tool copies the cel-shaded starter and
      // exports it. It needs a server-side run, so a small hidden turn starts it;
      // Play fills in when games/<id>.html arrives.
      const meta = { id, name, kind: 'godot', genre: null, art: null, description: '', controls: 'Move with WASD or the arrows, or drag on a touch screen.', updatedAt: new Date().toISOString() }
      await store().set(`games/${id}.json`, meta)
      await store().setText(`games/${id}.html`, '', { contentType: 'text/html' })
      await startGodotGame(meta)
      setGames((list) => [meta, ...list])
      setCurrentId(id)
      setTab('studio')
      return meta
    } catch {
      setLoadError('A new game could not be started. Try again.')
      return null
    } finally {
      setCreating(false)
    }
  }

  createBlankGameRef.current = createBlankGame

  // Inside a Game project: find (or, for a new project, start) its game and
  // stay on it. The minute sync then fills the project's files from the studio.
  useEffect(() => {
    if (!hostProjectId || !gamesLoaded) return undefined
    let alive = true
    ;(async () => {
      if (guestRef.current) {
        // A guest's storage holds exactly this project's game.
        const gid = games.find((g) => !isHiddenGame(g.id))?.id
        if (!gid) throw new Error('no game')
        if (!alive) return
        setHostGameId(gid)
        setCurrentId(gid)
        return
      }
      let gid = await gameForProject(hostProjectId)
      if (!gid) {
        gid = 'g-' + hostProjectId.replace(/[^a-z0-9]/gi, '').slice(0, 8).toLowerCase()
        const mine = await window.mobius?.projects?.list?.().catch(() => null)
        const name = (Array.isArray(mine) ? mine : mine?.projects || []).find((p) => p.id === hostProjectId)?.name || 'Untitled game'
        if (!(await store().get(`games/${gid}.json`))) {
          if (!(await createBlankGame({ id: gid, name }))) return
        }
        await store().set(`projects/${gid}.json`, { projectId: hostProjectId, root: `projects/${hostProjectId}`, name, synced: {}, createdAt: new Date().toISOString() })
      }
      if (!alive) return
      setHostGameId(gid)
      setCurrentId(gid)
    })().catch(() => alive && setLoadError("This project's game could not be opened. Try again."))
    return () => { alive = false }
  }, [hostProjectId, gamesLoaded])
  useEffect(() => {
    if (hostGameId && currentId !== hostGameId && games.some((g) => g.id === hostGameId)) setCurrentId(hostGameId)
  }, [hostGameId, currentId, games])

  // Sends one request to the current game's studio chat, as if typed there.
  const sendToGame = async (text, target = game) => {
    if (!target) throw new Error('Start a game first.')
    if (guestRef.current) {
      // The project page sends it to the guest's assistant and shows the reply.
      await window.mobius.chat.start({ ...(await modelFor('creative')), title: target.name, draft: text })
      setTab('studio')
      return
    }
    const saved = await store().get(`chats/${target.id}.json`).catch(() => null)
    if (saved?.id) {
      let timezone = 'UTC'
      try { timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' } catch {}
      const res = await fetch(`/api/chats/${encodeURIComponent(saved.id)}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: text, cid: `gs-${Date.now().toString(36)}`, timezone }),
      })
      if (!res.ok) throw new Error(res.status === 409 ? 'The studio agent is still working on the last request. Try again when it finishes.' : 'The studio chat did not accept that. Try again.')
    } else {
      const { chatId } = await window.mobius.chat.start({
        ...(await modelFor('creative')),
        scope: `game:${target.id}`, ownerVisible: false, title: target.name,
        systemPrompt: studioAgentPrompt({ appId, game: target }), draft: text,
      })
      await store().set(`chats/${target.id}.json`, { id: chatId })
    }
    markBusy(true)
    setChatKey((k) => k + 1)
    setTab('studio')
  }

  const restoreVersion = async (entry) => {
    const text = await store().getText(entry.file)
    if (typeof text !== 'string') return
    await store().setText(`games/${currentId}.html`, text, { contentType: 'text/html' })
    setHtml(text)
    setReloadKey((k) => k + 1)
    setShowVersions(false)
  }

  const goFullscreen = async () => {
    const frame = frameRef.current
    try {
      // Godot games restart in play mode when the studio fills the screen (the panel is a
      // preview), so they use the app-filling path rather than the frame's own full screen.
      if (game?.kind !== 'godot' && frame?.requestFullscreen) { await frame.requestFullscreen(); frame.contentWindow?.focus(); return }
    } catch {
      // Element fullscreen is unavailable (iOS); fall back to filling the app.
    }
    setFocus(true)
    window.mobius?.immersive?.set?.(true)
  }
  const exitFocus = () => {
    setFocus(false)
    window.mobius?.immersive?.set?.(false)
  }

  useEffect(() => { if (playVisible) setGameError(null) }, [playVisible])

  // Scene games (every new game): the studio shows the live scene editor.
  const isScene = game?.kind === 'scene'
  // A game with nothing in it yet (made before scenes existed) becomes an empty scene,
  // with a fresh assistant chat that knows how to build scenes.
  useEffect(() => {
    if (!game || game.kind || html !== '' || isHiddenGame(game.id)) return
    const meta = { ...game, kind: 'scene', controls: game.controls || 'Move with the stick, arrows or WASD; Space jumps.' }
    const scene = { ...EMPTY_SCENE, name: game.name || 'Untitled game' }
    Promise.all([
      store().set(`games/${game.id}.scene.json`, scene),
      store().setText(`games/${game.id}.html`, sceneDocument(scene, 'play'), { contentType: 'text/html' }),
      store().remove ? store().remove(`chats/${game.id}.json`).catch(() => {}) : null,
    ]).then(() => store().set(`games/${game.id}.json`, meta))
      .then(() => { setGames((list) => list.map((g) => (g.id === game.id ? meta : g))); setChatKey((k) => k + 1) })
      .catch(() => {})
  }, [game?.id, game?.kind, html])

  // The link appears in published/<id>.json (playUrl), which the studio already follows.
  const runShare = async (stop = false) => {
    if (!currentId || shareBusy || !window.mobius?.chat?.start) return
    if (game?.kind === 'godot') { setShareError('Godot games can only be played inside Game Studio for now.'); return }
    setShareBusy(true); setShareError('')
    const name = game?.name || 'this game'
    try {
      await window.mobius.chat.start({
        scope: `share:${currentId}:${Date.now()}`,
        ownerVisible: false,
        title: stop ? `Stop sharing ${name}` : `Share ${name} to play`,
        ...(await modelFor('quick')),
        systemPrompt: 'You share Game Studio games as public play links. Run the one command you are given with the Bash tool, then reply in one short sentence saying whether it worked. If it fails, say why in plain words. Do nothing else.',
        draft: `Run: python3 ${STUDIO_DIR}/share_game.py ${appId} ${currentId}${stop ? ' --stop' : ''}`,
      })
    } catch {
      setShareError('The link could not be started. Try again.')
      setShareBusy(false)
    }
  }
  useEffect(() => { setShareBusy(false) }, [published?.playUrl])
  useEffect(() => {
    if (!shareBusy) return undefined
    const timer = setTimeout(() => { setShareBusy(false); setShareError('This is taking a while. Close and check again in a minute.') }, 5 * 60 * 1000)
    return () => clearTimeout(timer)
  }, [shareBusy])

  const installApp = async () => {
    const text = await store().getText(`games/${currentId}.html`).catch(() => null)
    if (text) ensurePublished(currentId, text, true)
  }
  // A guest has none of these owner tools (sharing, installing as an app).
  const sceneMenu = guest ? null : (
    <div className="gs-more">
      <button type="button" className="gs-btn" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}>More{wishes.fresh > 0 && <span className="gs-wish-count" aria-label={`${wishes.fresh} new wishes`}>{wishes.fresh}</span>}</button>
      {menuOpen && (
        <div className="gs-menu" role="menu" onClick={() => setMenuOpen(false)}>
          {project?.projectId && <button type="button" role="menuitem" onClick={() => setShowTogether(true)}><Group aria-hidden="true" />Build together</button>}
          {project?.projectId && <button type="button" role="menuitem" onClick={() => setShowWishes(true)}><Check aria-hidden="true" />Wishes{wishes.fresh ? ` · ${wishes.fresh} new` : ''}</button>}
          {project?.projectId && !hostProjectId && <button type="button" role="menuitem" onClick={openProject}><Folder aria-hidden="true" />Open in Projects (history)</button>}
          <button type="button" role="menuitem" onClick={() => setShowShare(true)}><Group aria-hidden="true" />{published?.playUrl ? 'Share to play · on' : 'Share to play'}</button>
          {published?.appId && <button type="button" role="menuitem" onClick={openApp}><ExternalLink aria-hidden="true" />Open as its own app</button>}
          <button type="button" role="menuitem" disabled={publishing} onClick={installApp}><Play aria-hidden="true" />
            {publishing ? 'Installing as an app…' : published?.appId ? 'Update its app' : 'Install as its own app'}</button>
        </div>
      )}
    </div>
  )

  // ---- Godot builder controls (the old scene builder's toolbar) ----
  const postView = (msg) => frameRef.current?.contentWindow?.postMessage({ type: 'studio:view', ...msg }, '*')
  const setGodotCutTo = (h) => { setGodotCut(h); postView({ cmd: 'cut', on: h !== null, height: h ?? 0 }) }
  const selectGodot = (name) => { setGodotSelected(name); postView({ cmd: 'select', name: name || '' }); setGodotSheet(null) }
  const undoGodot = async () => {
    if (!currentId || godotUndoing || !window.mobius?.chat?.start) return
    setGodotUndoing(true)
    try {
      await window.mobius.chat.start({
        scope: `godot-undo:${currentId}:${Date.now()}`, ownerVisible: false, title: `Undo in ${game?.name || 'the game'}`, ...(await modelFor('quick')),
        systemPrompt: 'You undo the last step of a Game Studio game. Run the one command you are given with the Bash tool, then reply in one short sentence saying whether it worked. If it says there is nothing to undo, say so. Do nothing else.',
        draft: `Run: python3 ${STUDIO_DIR}/godot_build.py undo ${appId} ${currentId}`,
      })
    } catch { setGodotUndoing(false) }
  }
  const addToGodot = (kind, name) => {
    setGodotSheet(null)
    const where = godotSelected ? ` next to the selected ${godotSelected}` : ''
    sendToGame(`Add my ${kind} "${name}" to the scene${where}.`).catch(() => {})
  }

  const stage = (
    <div className="gs-stage">
      {focus && <button type="button" className="gs-exit" aria-label="Exit full screen" onClick={exitFocus}><X aria-hidden="true" /></button>}
      {srcDoc && playVisible ? (
        <iframe
          key={`${currentId}-${reloadKey}`}
          ref={frameRef}
          title={game ? `${game.name} game` : 'Game'}
          sandbox="allow-scripts allow-pointer-lock"
          allow="fullscreen *; gamepad *; autoplay *"
          srcDoc={srcDoc}
          onLoad={() => { visibilityRef.current?.sync(); if (!document.activeElement || document.activeElement === document.body) frameRef.current?.contentWindow?.focus() }}
        />
      ) : (
        <div className="gs-stage-empty">
          <div>
            {startFailed ? (
              <>
                <h2>This game could not start</h2>
                <p>{startInfo?.message || 'Its first build stopped before it finished.'}</p>
                <div className="gs-suggestions">
                  <button type="button" className="gs-suggestion" onClick={() => { setClock(Date.now()); startGodotGame(game, true).catch(() => {}) }}>Try again</button>
                </div>
              </>
            ) : startPending ? (
              <>
                <div className="gs-spinner" aria-hidden="true" />
                <h2>{startInfo.state === 'engine' ? `Getting the game engine ready… ${startInfo.pct || 0}%` : 'Setting up your game…'}</h2>
                <p>{startInfo.state === 'engine' ? 'Only your first game needs this one-time download.' : 'This takes a moment.'}</p>
              </>
            ) : html === '' && agentBusy ? (
              <>
                <div className="gs-spinner" aria-hidden="true" />
                <h2>Building your game…</h2>
                <p>The first playable version takes a few minutes and appears right here. You can keep chatting meanwhile.</p>
              </>
            ) : html === '' ? (
              <>
                <h2>What do you want to make?</h2>
                <p>Describe your game in the chat {wide ? 'on the right' : 'below'}, or start from one of these.</p>
                <div className="gs-suggestions">
                  {SUGGESTIONS.map(([label, request]) => (
                    <button key={label} type="button" className="gs-suggestion" onClick={() => sendToGame(request).catch((err) => setLoadError(err.message))}>{label}</button>
                  ))}
                </div>
              </>
            ) : <h2>{gamesLoaded && !games.length ? 'Setting up your studio…' : 'Loading…'}</h2>}
          </div>
        </div>
      )}
      {isGodot && srcDoc && playVisible && !focus && (
        <>
          <div className="gs-sc-tools">
            <div className="gs-sc-seg" role="group" aria-label="Mode">
              <button type="button" aria-pressed={!godotPlay} onClick={() => setGodotPlay(false)}><Pencil aria-hidden="true" />Edit</button>
              <button type="button" aria-pressed={godotPlay} onClick={() => { setGodotPlay(true); setGodotSheet(null) }}><Play aria-hidden="true" />Play</button>
            </div>
            <span className="gs-sc-spacer" />
            {!godotPlay && <>
              <button type="button" className="gs-sc-ic" aria-label="Undo the last step" disabled={godotUndoing || agentBusy} onClick={undoGodot}><Undo aria-hidden="true" /></button>
              <button type="button" className="gs-sc-ic" aria-label="See inside buildings" aria-pressed={godotCut !== null} onClick={() => setGodotCutTo(godotCut === null ? 2.2 : null)}><Eye aria-hidden="true" /></button>
              <button type="button" className="gs-sc-ic" aria-label="Show everything" onClick={() => postView({ cmd: 'home' })}><Home aria-hidden="true" /></button>
              <button type="button" className="gs-sc-ic" aria-label="What's in the scene" aria-expanded={godotSheet === 'list'} onClick={() => setGodotSheet(godotSheet === 'list' ? null : 'list')}><Menu aria-hidden="true" /></button>
              <button type="button" className="gs-sc-ic" aria-label="Add to the scene" aria-expanded={godotSheet === 'add'} onClick={() => setGodotSheet(godotSheet === 'add' ? null : 'add')}><Plus aria-hidden="true" /></button>
            </>}
            {godotPlay && <button type="button" className="gs-sc-ic" aria-label="Full screen" onClick={goFullscreen}><Expand aria-hidden="true" /></button>}
          </div>
          {!godotPlay && godotCut !== null && (
            <label className="gs-sc-cut">
              <span>See inside · cut at {godotCut.toFixed(1)} m</span>
              <input type="range" min={0.3} max={12} step={0.1} value={godotCut} onChange={(e) => setGodotCutTo(+e.target.value)} />
            </label>
          )}
          {(agentBusy || godotUndoing) && <div className="gs-sc-busy" role="status"><span className="gs-sc-dot" aria-hidden="true" />{godotUndoing ? 'Undoing…' : 'Building…'}</div>}
          {!godotPlay && godotSelected && !godotSheet && (
            <div className="gs-gd-selected" role="status">
              <Cube aria-hidden="true" /><span><b>{godotSelected}</b> is selected · ask the assistant about "this"</span>
              <button type="button" className="gs-sc-close" aria-label="Deselect" onClick={() => selectGodot(null)}><X aria-hidden="true" /></button>
            </div>
          )}
          {!godotPlay && godotSheet === 'list' && (
            <div className="gs-sc-sheet" role="region" aria-label="What's in the scene">
              <header><h3>In the scene</h3><button type="button" className="gs-sc-close" aria-label="Close" onClick={() => setGodotSheet(null)}><X aria-hidden="true" /></button></header>
              {godotObjects.length ? (
                <ul className="gs-sc-list">
                  {godotObjects.map((name) => (
                    <li key={name}><button type="button" className="gs-sc-row" aria-current={name === godotSelected} onClick={() => selectGodot(name)}><Cube aria-hidden="true" />{name}</button></li>
                  ))}
                </ul>
              ) : <p className="gs-hint">Nothing named yet. Ask the assistant to build something.</p>}
            </div>
          )}
          {!godotPlay && godotSheet === 'add' && (
            <div className="gs-sc-sheet" role="region" aria-label="Add to the scene">
              <header><h3>Add to the scene</h3><button type="button" className="gs-sc-close" aria-label="Close" onClick={() => setGodotSheet(null)}><X aria-hidden="true" /></button></header>
              <p className="gs-hint">The assistant places it{godotSelected ? ` next to ${godotSelected}` : ''}.</p>
              <div className="gs-sc-tiles">
                {Object.entries(assets.characters || {}).filter(([, c]) => c.kind === '3d').map(([name, c]) => (
                  <button key={`c-${name}`} type="button" className="gs-sc-tile" onClick={() => addToGodot('character', name)}>
                    {c.thumb ? <img src={c.thumb} alt="" /> : <User aria-hidden="true" />}{name}
                  </button>
                ))}
                {Object.keys(assets.models || {}).filter((name) => !assets.characters?.[name]).map((name) => (
                  <button key={`m-${name}`} type="button" className="gs-sc-tile" onClick={() => addToGodot('model', name)}><Cube aria-hidden="true" />{name}</button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )

  reloadAssetsRef.current = reloadAssets
  // A guest's chat is their own assistant, shown by the project page beside the studio.
  const createPanel = game && !guest ? <StudioChat key={`${game.id}-${chatKey}`} appId={appId} game={game} onTurnDone={onTurnDone} onSent={() => markBusy(true)} /> : null
  const assetsPanel = <AssetsPanel appId={appId} assets={assets} onRefresh={reloadAssets} onUse={setUseRequest} onChange={saveAssets} guest={guest} models={modelActions} voice={{ mode: voiceMode, setMode: changeVoiceMode, say: (text, opts) => voiceRef.current.say(text, opts) }} />

  // Inside a project, show nothing of another game while its own is found.
  if (hostProjectId && (!hostGameId || currentId !== hostGameId)) {
    return (
      <div className="gs-root">
        <style>{CSS}</style>
        <header className="gs-top"><div className="gs-logo" aria-hidden="true" /><h1 className="gs-title">Opening your game…</h1></header>
        {loadError && <p className="gs-error" role="alert" style={{ margin: '0 16px 8px' }}>{loadError}</p>}
      </div>
    )
  }

  // Deletes this game's files, its chat, its published link and its project link.
  // Nothing is removed until the owner confirms in the dialog below.
  const deleteGame = async (id) => {
    const target = games.find((g) => g.id === id)
    const keys = [`games/${id}.html`, `games/${id}.json`, `games/${id}.art.json`, `games/${id}.scene.json`,
      `games/${id}.saves.json`, `games/${id}.pck`, `games/${id}.start.json`, `chats/${id}.json`, `published/${id}.json`, `projects/${id}.json`]
    await Promise.all(keys.map((k) => store().remove(k).catch(() => {})))
    // Godot builds: one game file per build (games/<id>.<build>.pck)
    const listed = await store().listWithStatus('games/').catch(() => ({ entries: [] }))
    await Promise.all((listed.entries || []).filter((e) => e.type === 'file' && e.name.startsWith(`${id}.`) && e.name.endsWith('.pck'))
      .map((e) => store().remove(`games/${e.name}`).catch(() => {})))
    setGames((list) => {
      const rest = list.filter((g) => g.id !== id)
      setCurrentId((cur) => (cur === id ? rest[0]?.id ?? null : cur))
      return rest
    })
    setConfirmDelete(null)
    return target?.name
  }

  return (
    <div className={`gs-root${focus ? ' is-focus' : ''}${hostProjectId ? ' is-hosted' : ''}${hostTabs ? ' is-host-tabs' : ''}`}>
      <style>{CSS + SCENE_CSS + REQUESTS_CSS}</style>
      {/* Inside a project, the project's own bar already names the game. */}
      {!hostProjectId && <header className="gs-top">
        <div className="gs-logo" aria-hidden="true" />
        <>
        <label className="gs-picker">
          <span className="gs-visually-hidden">Your game</span>
          <select value={currentId || ''} onChange={(e) => { setCurrentId(e.target.value); setTab('studio') }}>
            {games.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </select>
        </label>
        <button type="button" className="gs-new" disabled={creating} onClick={() => createBlankGame()}><Plus aria-hidden="true" />New game</button>
        {currentId && (confirmDelete === currentId ? (
          <span className="gs-confirm-delete" role="alertdialog" aria-label="Confirm delete">
            Delete “{game?.name || 'this game'}” for good?
            <button type="button" className="gs-btn gs-btn--danger" onClick={() => deleteGame(currentId)}>Delete</button>
            <button type="button" className="gs-btn" onClick={() => setConfirmDelete(null)}>Keep</button>
          </span>
        ) : (
          <button type="button" className="gs-delete-game" onClick={() => setConfirmDelete(currentId)}>Delete game</button>
        ))}
        </>
      </header>}
      {loadError && <p className="gs-error" role="alert" style={{ margin: '0 16px 8px' }}>{loadError}</p>}
      {!hostTabs && <nav className="gs-tabs" role="tablist" aria-label="Studio">
        {[['studio', hostProjectId ? (isScene ? 'Scene' : 'Game') : 'Studio', Play], ['characters', 'Characters', User], ['assets', 'Assets', Cube]].map(([key, label, Icon]) => (
          <button key={key} type="button" role="tab" className="gs-tab" aria-selected={tab === key} onClick={() => setTab(key)}><Icon aria-hidden="true" />{label}</button>
        ))}
      </nav>}
      <main className="gs-body">
        <section className="gs-panel gs-panel--build" data-panel="play" hidden={tab !== 'studio'}>
          {isScene ? (
            <SceneEditor gameId={currentId} models={modelData.data} modelsReady={modelData.key === modelKey && audioData.key === soundKey && artReady}
              assets={library} art={withLibrary(art.value, library)} saves={savesRef.current} busy={agentBusy} turnSignal={turnSignal}
              onError={(err) => setGameError(err)} onSuggest={(text) => sendToGame(text).catch((err) => setLoadError(err.message))}
              suggestions={SCENE_SUGGESTIONS} menu={sceneMenu} />
          ) : stage}
          {game && html && !isScene && (
            <div className="gs-bar">
              {isGodot
                ? <span className="gs-controls-hint">{godotPlay ? (game?.controls || 'Playing in the panel') : 'Tap to select · drag to look around · pinch to zoom'}</span>
                : <>
                  <button type="button" className="gs-btn gs-btn--primary gs-btn--play" onClick={goFullscreen} disabled={!srcDoc}><Play aria-hidden="true" />Play</button>
                  {game?.controls && <span className="gs-controls-hint">{game.controls}</span>}
                </>}
              {wishes.fresh > 0 && <button type="button" className="gs-btn gs-wish-btn" onClick={() => setShowWishes(true)}>Wishes <span className="gs-wish-count" aria-label={`${wishes.fresh} new`}>{wishes.fresh}</span></button>}
              <div className="gs-more">
                <button type="button" className="gs-btn" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((v) => !v)}>More{wishes.fresh > 0 && <span className="gs-wish-count" aria-label={`${wishes.fresh} new wishes`}>{wishes.fresh}</span>}</button>
                {menuOpen && (
                  <div className="gs-menu" role="menu" onClick={() => setMenuOpen(false)}>
                    <button type="button" role="menuitem" onClick={() => { setGameError(null); setReloadKey((k) => k + 1) }}><Reload aria-hidden="true" />Restart the game</button>
                    <button type="button" role="menuitem" onClick={() => setShowVersions(true)}><History aria-hidden="true" />Go back to an earlier version</button>
                    {project?.projectId && <button type="button" role="menuitem" onClick={() => setShowTogether(true)}><Group aria-hidden="true" />Build together</button>}
                    {project?.projectId && <button type="button" role="menuitem" onClick={() => setShowWishes(true)}><Check aria-hidden="true" />Wishes{wishes.fresh ? ` · ${wishes.fresh} new` : ''}</button>}
                    {project?.projectId && !hostProjectId && <button type="button" role="menuitem" onClick={openProject}><Folder aria-hidden="true" />Open in Projects</button>}
                    {!guest && !isHiddenGame(game?.id) && <button type="button" role="menuitem" onClick={() => setShowShare(true)}><Group aria-hidden="true" />{published?.playUrl ? 'Share to play · on' : 'Share to play'}</button>}
                    {!guest && !isHiddenGame(game?.id) && (published?.appId
                      ? <button type="button" role="menuitem" onClick={openApp}><ExternalLink aria-hidden="true" />{publishing ? 'Open as its own app (updating…)' : 'Open as its own app'}</button>
                      : <span className="gs-menu-note">{publishing ? 'Turning it into its own app…' : 'It becomes its own app after your first change.'}</span>)}
                  </div>
                )}
              </div>
            </div>
          )}
          {art.missing && artReady && (
            <div className="gs-banner gs-banner--info" role="status">
              <p><b>This style's art isn't installed yet</b>, so the game uses simple shapes. Ask in the chat below: "install the art".</p>
            </div>
          )}
          {gameError && (
            <div className="gs-banner" role="alert">
              <p><b>The game hit an error:</b> {gameError.message}. Ask in the chat below to fix it; the AI can see this error.</p>
              <button type="button" className="gs-icon-btn" aria-label="Dismiss error" onClick={() => setGameError(null)}><X aria-hidden="true" /></button>
            </div>
          )}
          {showVersions && (
            <div className="gs-versions">
              <h3>Versions</h3>
              {versions.length ? (
                <ul>
                  {versions.map((v, i) => (
                    <li key={v.file}>
                      <span>{new Date(v.at).toLocaleString()}{i === 0 ? ' · current' : ''}</span>
                      {i > 0 && <button type="button" className="gs-btn" onClick={() => restoreVersion(v)}>Restore</button>}
                    </li>
                  ))}
                </ul>
              ) : <p className="gs-hint">Each change the agent makes is saved here.</p>}
            </div>
          )}
          {!wide && createPanel && <div className="gs-build-chat">{createPanel}</div>}
        </section>
        {wide && <aside className="gs-side" hidden={tab !== 'studio'}>{createPanel}</aside>}
        <section className="gs-panel gs-panel--page" hidden={tab !== 'characters'}>
          <CharactersPanel appId={appId} token={token} assets={assets} onRefresh={reloadAssets} onSaveAssets={updateAssets} onUse={setUseRequest} guest={guest} />
        </section>
        <section className="gs-panel gs-panel--page" hidden={tab !== 'assets'}>{assetsPanel}</section>
      </main>
      {showWishes && <RequestsSheet gameName={game?.name} board={board.board} notes={notes} onDecide={board.decide}
        onAsk={(item) => sendToGame(askMessage(item))} onAskNote={(note) => sendToGame(noteMessage(note))} onOpenProject={() => { openProject(); setShowWishes(false) }} onClose={() => setShowWishes(false)} />}
      {showShare && <SharePlaySheet gameName={game?.name} playUrl={published?.playUrl} busy={shareBusy} error={shareError} onShare={() => runShare(false)} onStop={() => runShare(true)} onClose={() => setShowShare(false)} />}
      {showTogether && <BuildTogetherSheet gameName={game?.name} onOpen={() => { openProject(); setShowTogether(false) }} onClose={() => setShowTogether(false)} />}
      <UseInGameSheet request={useRequest} gameName={game?.name} onClose={() => setUseRequest(null)}
        onSend={async (text) => { await sendToGame(text); setUseRequest(null) }} />
    </div>
  )
}
