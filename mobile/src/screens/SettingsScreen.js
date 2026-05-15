import React, { useState, useCallback } from 'react';
import {
    View, ScrollView, StyleSheet, Text, TextInput,
    TouchableOpacity, Alert,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { loadConfig, saveConfig, health } from '../api/empire';

const C = {
    bg: '#0f172a', card: '#1e293b', border: '#334155',
    text: '#e2e8f0', muted: '#94a3b8',
    green: '#22c55e', blue: '#3b82f6', red: '#ef4444',
};

function Field({ label, hint, value, onChangeText, secure = false, mono = false }) {
    return (
        <View style={styles.field}>
            <Text style={styles.fieldLabel}>{label}</Text>
            {hint ? <Text style={styles.fieldHint}>{hint}</Text> : null}
            <TextInput
                style={[styles.fieldInput, mono && styles.mono]}
                value={value}
                onChangeText={onChangeText}
                autoCapitalize="none"
                autoCorrect={false}
                secureTextEntry={secure}
                placeholderTextColor={C.muted}
            />
        </View>
    );
}

export default function SettingsScreen() {
    const [bridgeUrl, setBridgeUrl] = useState('');
    const [bridgeKey, setBridgeKey] = useState('');
    const [storeUrl,  setStoreUrl]  = useState('');
    const [saved,     setSaved]     = useState(false);
    const [testing,   setTesting]   = useState(false);

    useFocusEffect(useCallback(() => {
        loadConfig().then(cfg => {
            setBridgeUrl(cfg.bridgeUrl);
            setBridgeKey(cfg.bridgeKey);
            setStoreUrl(cfg.storeUrl);
        });
    }, []));

    const handleSave = async () => {
        await saveConfig({ bridgeUrl, bridgeKey, storeUrl });
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
    };

    const handleTest = async () => {
        setTesting(true);
        try {
            const h = await health();
            Alert.alert('Connection OK', `Bridge responded:\nStatus: ${h.status}\nTime: ${h.timestamp}`);
        } catch (e) {
            Alert.alert(
                'Connection Failed',
                `Cannot reach bridge at:\n${bridgeUrl}\n\nError: ${e.message}\n\n` +
                'Make sure the Termux bridge is running:\n' +
                '  python3 termux_bridge.py\n\n' +
                'Or set the Cloudflare tunnel URL if connecting remotely.',
            );
        } finally {
            setTesting(false);
        }
    };

    return (
        <ScrollView style={styles.container} contentContainerStyle={styles.content}>
            <Text style={styles.heading}>Connection</Text>
            <Text style={styles.description}>
                The app connects to the Termux bridge running on your phone.{'\n'}
                On the same device, use <Text style={styles.code}>http://localhost:8001</Text>.{'\n'}
                From another device, use your Cloudflare tunnel URL.
            </Text>

            <Field
                label="Bridge URL"
                hint="Termux bridge — default http://localhost:8001"
                value={bridgeUrl}
                onChangeText={setBridgeUrl}
                mono
            />

            <Field
                label="Bridge API Key"
                hint="Value of BRIDGE_API_KEY in your .env"
                value={bridgeKey}
                onChangeText={setBridgeKey}
                secure
                mono
            />

            <Field
                label="Store URL"
                hint="Storefront — default http://localhost:8000"
                value={storeUrl}
                onChangeText={setStoreUrl}
                mono
            />

            {/* Buttons */}
            <TouchableOpacity
                style={[styles.button, styles.testButton]}
                onPress={handleTest}
                disabled={testing}
            >
                <Text style={styles.testButtonText}>
                    {testing ? 'Testing…' : 'Test Connection'}
                </Text>
            </TouchableOpacity>

            <TouchableOpacity
                style={[styles.button, styles.saveButton, saved && styles.savedButton]}
                onPress={handleSave}
            >
                <Text style={styles.saveButtonText}>
                    {saved ? '✓ Saved' : 'Save Settings'}
                </Text>
            </TouchableOpacity>

            <View style={styles.divider} />

            <Text style={styles.heading}>Quick Setup</Text>
            <Text style={styles.description}>
                Run these in Termux to start the bridge:{'\n\n'}
                <Text style={styles.code}>cd ~/publishing-empire{'\n'}python3 termux_bridge.py</Text>
            </Text>

            <Text style={styles.description}>
                To use remotely, update the Cloudflare tunnel URL above.{'\n'}
                Your tunnel URL comes from:{'\n'}
                <Text style={styles.code}>pm2 logs CF-Tunnel</Text>
            </Text>
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container:      { flex: 1, backgroundColor: C.bg },
    content:        { padding: 16, paddingBottom: 60 },
    heading:        { fontSize: 18, fontWeight: '700', color: C.text, marginBottom: 8 },
    description:    { color: C.muted, fontSize: 13, lineHeight: 20, marginBottom: 16 },
    code:           { fontFamily: 'monospace', color: C.text, backgroundColor: '#1e293b' },
    divider:        { height: 1, backgroundColor: C.border, marginVertical: 24 },
    field:          { marginBottom: 16 },
    fieldLabel:     { color: C.text, fontWeight: '600', fontSize: 13, marginBottom: 4 },
    fieldHint:      { color: C.muted, fontSize: 11, marginBottom: 6 },
    fieldInput:     { backgroundColor: C.card, color: C.text, borderRadius: 10,
                      paddingHorizontal: 14, paddingVertical: 10, fontSize: 14,
                      borderWidth: 1, borderColor: C.border },
    mono:           { fontFamily: 'monospace', fontSize: 12 },
    button:         { borderRadius: 12, paddingVertical: 14, alignItems: 'center',
                      marginBottom: 12 },
    testButton:     { backgroundColor: C.card, borderWidth: 1, borderColor: C.blue },
    testButtonText: { color: C.blue, fontWeight: '600', fontSize: 15 },
    saveButton:     { backgroundColor: C.blue },
    savedButton:    { backgroundColor: C.green },
    saveButtonText: { color: '#fff', fontWeight: '700', fontSize: 15 },
});
