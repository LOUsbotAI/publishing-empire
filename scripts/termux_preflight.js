#!/usr/bin/env node
/**
 * LOUSTA Termux Pre-flight Check
 *
 * Run this before any book generation job to prevent scaffold content.
 * If the Anthropic key is invalid, generation WILL produce placeholder
 * text that looks real but is worthless. This catches it first.
 *
 * Usage:   node termux_preflight.js
 * Exit 0:  all critical APIs live — safe to generate
 * Exit 1:  critical failure — abort generation, fix keys first
 *
 * Wire into PM2 ecosystem or call at the top of each generator script:
 *   const { execSync } = require('child_process');
 *   execSync('node ~/publishing-empire/scripts/termux_preflight.js', { stdio: 'inherit' });
 */

const https = require('https');
const fs   = require('fs');
const path = require('path');

// ─── Load .env from canonical Termux vault location ──────────────────────────
const envPath = path.join(process.env.HOME, '.lousta_system_core/secrets/.env');
if (fs.existsSync(envPath)) {
    fs.readFileSync(envPath, 'utf8').split('\n').forEach(line => {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#') && trimmed.includes('=')) {
            const eq = trimmed.indexOf('=');
            const k  = trimmed.slice(0, eq).trim();
            const v  = trimmed.slice(eq + 1).trim().replace(/^["']|["']$/g, '');
            if (!process.env[k]) process.env[k] = v;
        }
    });
}

// Support both naming conventions used across the Termux/Python split
const ANTHROPIC_KEY   = process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_KEY   || '';
const GEMINI_KEY      = process.env.GEMINI_API_KEY    || process.env.GEMINI_KEY       || '';
const ELEVENLABS_KEY  = process.env.ELEVENLABS_API_KEY                                 || '';

const P = '✅';
const F = '❌';
const W = '⚠️ ';

let criticalFailure = false;

// ─── Helpers ─────────────────────────────────────────────────────────────────

function post(hostname, path, headers, body) {
    return new Promise((resolve, reject) => {
        const buf = Buffer.from(body);
        const req = https.request(
            { hostname, path, method: 'POST', headers: { ...headers, 'Content-Length': buf.length } },
            res => {
                let data = '';
                res.on('data', c => data += c);
                res.on('end', () => resolve({ status: res.statusCode, body: data }));
            }
        );
        req.on('error', reject);
        req.setTimeout(15000, () => { req.destroy(); reject(new Error('timeout')); });
        req.write(buf);
        req.end();
    });
}

function get(hostname, path, headers) {
    return new Promise((resolve, reject) => {
        const req = https.request(
            { hostname, path, method: 'GET', headers },
            res => {
                let data = '';
                res.on('data', c => data += c);
                res.on('end', () => resolve({ status: res.statusCode, body: data }));
            }
        );
        req.on('error', reject);
        req.setTimeout(10000, () => { req.destroy(); reject(new Error('timeout')); });
        req.end();
    });
}

// ─── Checks ──────────────────────────────────────────────────────────────────

async function checkAnthropic() {
    if (!ANTHROPIC_KEY || !ANTHROPIC_KEY.startsWith('sk-ant')) {
        console.error(`${F} ANTHROPIC_API_KEY — missing or wrong format`);
        criticalFailure = true;
        return;
    }
    try {
        const r = await post(
            'api.anthropic.com',
            '/v1/messages',
            {
                'Content-Type': 'application/json',
                'x-api-key': ANTHROPIC_KEY,
                'anthropic-version': '2023-06-01',
            },
            JSON.stringify({
                model: 'claude-haiku-4-5-20251001',
                max_tokens: 5,
                messages: [{ role: 'user', content: 'ping' }],
            })
        );
        if (r.status === 200) {
            console.log(`${P} Anthropic API — live`);
        } else {
            const msg = JSON.parse(r.body).error?.message || `HTTP ${r.status}`;
            console.error(`${F} Anthropic API — ${msg}`);
            criticalFailure = true;
        }
    } catch (e) {
        console.error(`${F} Anthropic API — ${e.message}`);
        criticalFailure = true;
    }
}

async function checkGemini() {
    if (!GEMINI_KEY || !GEMINI_KEY.startsWith('AIza')) {
        console.warn(`${W} GEMINI_API_KEY — missing (Gemini features disabled)`);
        return;
    }
    try {
        const r = await post(
            'generativelanguage.googleapis.com',
            `/v1beta/models/gemini-pro:generateContent?key=${GEMINI_KEY}`,
            { 'Content-Type': 'application/json' },
            JSON.stringify({ contents: [{ parts: [{ text: 'ping' }] }] })
        );
        if (r.status === 200) {
            console.log(`${P} Gemini API — live`);
        } else {
            const msg = JSON.parse(r.body).error?.message || `HTTP ${r.status}`;
            console.warn(`${W} Gemini API — ${msg}`);
        }
    } catch (e) {
        console.warn(`${W} Gemini API — ${e.message}`);
    }
}

async function checkElevenLabs() {
    if (!ELEVENLABS_KEY) {
        console.warn(`${W} ELEVENLABS_API_KEY — missing (audiobooks will be silent stubs)`);
        return;
    }
    try {
        const r = await get('api.elevenlabs.io', '/v1/user', { 'xi-api-key': ELEVENLABS_KEY });
        if (r.status === 200) {
            const sub = JSON.parse(r.body).subscription || {};
            const remaining = (sub.character_limit || 0) - (sub.character_count || 0);
            console.log(`${P} ElevenLabs — ${remaining.toLocaleString()} chars remaining`);
            if (remaining < 10000) {
                console.warn(`${W} ElevenLabs quota low: only ${remaining.toLocaleString()} chars left`);
            }
        } else {
            console.warn(`${W} ElevenLabs — HTTP ${r.status}`);
        }
    } catch (e) {
        console.warn(`${W} ElevenLabs — ${e.message}`);
    }
}

// ─── Main ─────────────────────────────────────────────────────────────────────

async function main() {
    console.log('\n' + '='.repeat(52));
    console.log('  LOUSTA PRE-FLIGHT CHECK');
    console.log('  Validating API keys before generation...');
    console.log('='.repeat(52));

    await checkAnthropic();
    await checkGemini();
    await checkElevenLabs();

    console.log('='.repeat(52));

    if (criticalFailure) {
        console.error(`\n${F} ABORTING — Anthropic API is unavailable.`);
        console.error('  Books generated without a valid key produce scaffold text.');
        console.error('\n  Fix:');
        console.error('    bash ~/publishing-empire/scripts/update_keys.sh');
        console.error('    pm2 restart all\n');
        process.exit(1);
    }

    console.log(`\n${P} All critical APIs live — generation is safe.\n`);
    process.exit(0);
}

main().catch(e => {
    console.error('Pre-flight error:', e.message);
    process.exit(1);
});
