/**
 * Empire API client.
 * Connects to the Termux bridge (port 8001) and storefront (port 8000).
 * All config is stored in AsyncStorage — set it once in the Settings screen.
 *
 * Default URL: http://localhost:8001  (works when Expo runs on the phone itself)
 * Remote URL:  your Cloudflare tunnel URL  (works from any device)
 */
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';

const DEFAULT_URL   = 'http://localhost:8001';
const DEFAULT_STORE = 'http://localhost:8000';

async function _bridge() {
    const [url, key] = await Promise.all([
        AsyncStorage.getItem('bridge_url'),
        AsyncStorage.getItem('bridge_key'),
    ]);
    return axios.create({
        baseURL: url || DEFAULT_URL,
        timeout: 12000,
        headers: {
            'Content-Type': 'application/json',
            'X-Bridge-Key': key || '',
        },
    });
}

async function _store() {
    const url = await AsyncStorage.getItem('store_url');
    return axios.create({
        baseURL: url || DEFAULT_STORE,
        timeout: 12000,
        headers: { 'Content-Type': 'application/json' },
    });
}

// ─── Health ───────────────────────────────────────────────────────────────────

export async function health() {
    const api = await _bridge();
    const r   = await api.get('/bridge/health');
    return r.data;
}

// ─── Revenue ─────────────────────────────────────────────────────────────────

export async function getRevenue() {
    const api = await _bridge();
    const r   = await api.get('/bridge/revenue');
    return r.data;
}

// ─── Catalogue ───────────────────────────────────────────────────────────────

export async function getCatalogue() {
    const api = await _bridge();
    const r   = await api.get('/bridge/catalogue');
    return r.data;                  // { products: [...], count: N }
}

// ─── Jobs ─────────────────────────────────────────────────────────────────────

export async function getPendingJobs() {
    const api = await _bridge();
    const r   = await api.get('/bridge/pending_jobs');
    return r.data;                  // { jobs: [...] }
}

// ─── Store products (public, no key needed) ───────────────────────────────────

export async function getStoreProducts() {
    const api = await _store();
    const r   = await api.get('/store');
    return r.data;
}

// ─── Config helpers ───────────────────────────────────────────────────────────

export async function saveConfig({ bridgeUrl, bridgeKey, storeUrl }) {
    await AsyncStorage.multiSet([
        ['bridge_url',  bridgeUrl  || DEFAULT_URL],
        ['bridge_key',  bridgeKey  || ''],
        ['store_url',   storeUrl   || DEFAULT_STORE],
    ]);
}

export async function loadConfig() {
    const [[, bridgeUrl], [, bridgeKey], [, storeUrl]] = await AsyncStorage.multiGet([
        'bridge_url', 'bridge_key', 'store_url',
    ]);
    return {
        bridgeUrl:  bridgeUrl  || DEFAULT_URL,
        bridgeKey:  bridgeKey  || '',
        storeUrl:   storeUrl   || DEFAULT_STORE,
    };
}
