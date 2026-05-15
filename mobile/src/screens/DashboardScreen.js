import React, { useState, useCallback } from 'react';
import {
    View, ScrollView, StyleSheet, RefreshControl, Text,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { getRevenue, getPendingJobs, health } from '../api/empire';

const C = {
    bg:      '#0f172a',
    card:    '#1e293b',
    border:  '#334155',
    text:    '#e2e8f0',
    muted:   '#94a3b8',
    green:   '#22c55e',
    blue:    '#3b82f6',
    yellow:  '#eab308',
    red:     '#ef4444',
};

function MetricCard({ label, value, sub, color = C.green }) {
    return (
        <View style={[styles.card, styles.metricCard]}>
            <Text style={[styles.metricValue, { color }]}>{value}</Text>
            <Text style={styles.metricLabel}>{label}</Text>
            {sub ? <Text style={styles.metricSub}>{sub}</Text> : null}
        </View>
    );
}

function PlatformRow({ platform, total, sales }) {
    return (
        <View style={styles.platformRow}>
            <Text style={styles.platformName}>{platform}</Text>
            <View style={styles.platformRight}>
                <Text style={styles.platformSales}>{sales} sales</Text>
                <Text style={styles.platformTotal}>${Number(total).toFixed(2)}</Text>
            </View>
        </View>
    );
}

function JobRow({ job }) {
    const statusColor = job.status === 'pending' ? C.yellow
                      : job.status === 'running' ? C.blue
                      : C.green;
    return (
        <View style={styles.jobRow}>
            <View style={[styles.jobDot, { backgroundColor: statusColor }]} />
            <View style={{ flex: 1 }}>
                <Text style={styles.jobTitle} numberOfLines={1}>
                    {job.niche} / {job.language} — {job.pipeline}
                </Text>
                <Text style={styles.jobStatus}>{job.status}</Text>
            </View>
        </View>
    );
}

export default function DashboardScreen() {
    const [revenue,  setRevenue]  = useState(null);
    const [jobs,     setJobs]     = useState([]);
    const [apiOk,    setApiOk]    = useState(null);
    const [loading,  setLoading]  = useState(true);
    const [lastSync, setLastSync] = useState(null);
    const [error,    setError]    = useState('');

    const load = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const [rev, j, h] = await Promise.allSettled([
                getRevenue(),
                getPendingJobs(),
                health(),
            ]);
            if (rev.status === 'fulfilled')  setRevenue(rev.value);
            if (j.status   === 'fulfilled')  setJobs(j.value.jobs || []);
            setApiOk(h.status === 'fulfilled');
            setLastSync(new Date().toLocaleTimeString());
        } catch (e) {
            setError('Cannot reach bridge. Check Settings → Bridge URL.');
            setApiOk(false);
        } finally {
            setLoading(false);
        }
    }, []);

    useFocusEffect(useCallback(() => { load(); }, [load]));

    const totalUSD    = revenue?.all_time_usd ?? 0;
    const byPlatform  = revenue?.by_platform  ?? [];
    const pendingJobs = jobs.filter(j => j.status === 'pending').length;
    const runningJobs = jobs.filter(j => j.status === 'running').length;

    return (
        <ScrollView
            style={styles.container}
            contentContainerStyle={styles.content}
            refreshControl={
                <RefreshControl refreshing={loading} onRefresh={load}
                    tintColor={C.blue} colors={[C.blue]} />
            }
        >
            {/* Header */}
            <View style={styles.header}>
                <Text style={styles.heading}>Publishing Empire</Text>
                <View style={[styles.statusDot,
                    { backgroundColor: apiOk === null ? C.muted : apiOk ? C.green : C.red }]} />
            </View>
            {lastSync ? <Text style={styles.syncTime}>Last sync: {lastSync}</Text> : null}
            {error ? <Text style={styles.errorText}>{error}</Text> : null}

            {/* Revenue metrics */}
            <Text style={styles.sectionLabel}>REVENUE</Text>
            <View style={styles.metricsRow}>
                <MetricCard
                    label="All Time (USD)"
                    value={`$${Number(totalUSD).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
                    color={C.green}
                />
                <MetricCard
                    label="Pending Jobs"
                    value={String(pendingJobs)}
                    sub={runningJobs ? `${runningJobs} running` : null}
                    color={pendingJobs > 0 ? C.yellow : C.muted}
                />
            </View>

            {/* By platform */}
            {byPlatform.length > 0 && (
                <>
                    <Text style={styles.sectionLabel}>BY PLATFORM</Text>
                    <View style={styles.card}>
                        {byPlatform.map((p, i) => (
                            <PlatformRow key={i} platform={p.platform}
                                total={p.total} sales={p.sales} />
                        ))}
                    </View>
                </>
            )}

            {/* Active jobs */}
            {jobs.length > 0 && (
                <>
                    <Text style={styles.sectionLabel}>JOBS</Text>
                    <View style={styles.card}>
                        {jobs.slice(0, 10).map((j, i) => (
                            <JobRow key={i} job={j} />
                        ))}
                    </View>
                </>
            )}
        </ScrollView>
    );
}

const styles = StyleSheet.create({
    container:    { flex: 1, backgroundColor: C.bg },
    content:      { padding: 16, paddingBottom: 40 },
    header:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
    heading:      { fontSize: 22, fontWeight: '700', color: C.text },
    statusDot:    { width: 10, height: 10, borderRadius: 5 },
    syncTime:     { fontSize: 11, color: C.muted, marginBottom: 16 },
    errorText:    { color: C.red, fontSize: 13, marginBottom: 12, padding: 10,
                    backgroundColor: '#2d1515', borderRadius: 8 },
    sectionLabel: { fontSize: 11, fontWeight: '600', color: C.muted, letterSpacing: 1,
                    marginTop: 20, marginBottom: 8 },
    card:         { backgroundColor: C.card, borderRadius: 12, padding: 14,
                    borderWidth: 1, borderColor: C.border },
    metricsRow:   { flexDirection: 'row', gap: 12 },
    metricCard:   { flex: 1 },
    metricValue:  { fontSize: 24, fontWeight: '700', marginBottom: 4 },
    metricLabel:  { fontSize: 12, color: C.muted },
    metricSub:    { fontSize: 11, color: C.muted, marginTop: 2 },
    platformRow:  { flexDirection: 'row', justifyContent: 'space-between',
                    alignItems: 'center', paddingVertical: 8,
                    borderBottomWidth: 1, borderColor: C.border },
    platformName: { color: C.text, fontSize: 14 },
    platformRight:{ alignItems: 'flex-end' },
    platformTotal:{ color: C.green, fontSize: 15, fontWeight: '600' },
    platformSales:{ color: C.muted, fontSize: 11 },
    jobRow:       { flexDirection: 'row', alignItems: 'center', paddingVertical: 8,
                    borderBottomWidth: 1, borderColor: C.border, gap: 10 },
    jobDot:       { width: 8, height: 8, borderRadius: 4 },
    jobTitle:     { color: C.text, fontSize: 13 },
    jobStatus:    { color: C.muted, fontSize: 11, marginTop: 2 },
});
