import React, { useState, useCallback } from 'react';
import {
    View, FlatList, StyleSheet, Text, TextInput, TouchableOpacity, RefreshControl,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import { getCatalogue } from '../api/empire';

const C = {
    bg: '#0f172a', card: '#1e293b', border: '#334155',
    text: '#e2e8f0', muted: '#94a3b8',
    green: '#22c55e', blue: '#3b82f6', purple: '#a78bfa',
};

const TYPE_COLOR = {
    audiobook: C.purple,
    ebook:     C.blue,
    video_long:  '#f59e0b',
    video_short: '#f59e0b',
};

const LANG_FLAG = {
    en: '🇬🇧', es: '🇪🇸', pt: '🇧🇷', de: '🇩🇪',
    fr: '🇫🇷', it: '🇮🇹', ja: '🇯🇵', zh: '🇨🇳',
    ko: '🇰🇷', ar: '🇸🇦',
};

function BookCard({ item }) {
    const typeColor = TYPE_COLOR[item.type] || C.muted;
    const flag      = LANG_FLAG[item.language] || item.language?.toUpperCase();
    return (
        <View style={styles.card}>
            <View style={styles.cardTop}>
                <View style={[styles.typeBadge, { backgroundColor: typeColor + '22' }]}>
                    <Text style={[styles.typeText, { color: typeColor }]}>
                        {item.type}
                    </Text>
                </View>
                <Text style={styles.flag}>{flag}</Text>
                <Text style={styles.price}>${Number(item.price_usd).toFixed(2)}</Text>
            </View>
            <Text style={styles.title} numberOfLines={2}>{item.title}</Text>
            {item.subtitle ? (
                <Text style={styles.subtitle} numberOfLines={1}>{item.subtitle}</Text>
            ) : null}
            {item.niche ? (
                <Text style={styles.niche}>{item.niche}</Text>
            ) : null}
        </View>
    );
}

export default function CatalogueScreen() {
    const [allProducts, setAllProducts] = useState([]);
    const [query,       setQuery]       = useState('');
    const [typeFilter,  setTypeFilter]  = useState('all');
    const [loading,     setLoading]     = useState(true);
    const [error,       setError]       = useState('');

    const load = useCallback(async () => {
        setLoading(true);
        setError('');
        try {
            const data = await getCatalogue();
            setAllProducts(data.products || []);
        } catch (e) {
            setError('Cannot load catalogue. Check Settings → Bridge URL.');
        } finally {
            setLoading(false);
        }
    }, []);

    useFocusEffect(useCallback(() => { load(); }, [load]));

    const types = ['all', ...Array.from(new Set(allProducts.map(p => p.type))).sort()];

    const visible = allProducts.filter(p => {
        const matchType = typeFilter === 'all' || p.type === typeFilter;
        const matchQ    = !query || p.title.toLowerCase().includes(query.toLowerCase())
                                 || (p.niche || '').toLowerCase().includes(query.toLowerCase());
        return matchType && matchQ;
    });

    return (
        <View style={styles.container}>
            {/* Search */}
            <View style={styles.searchBar}>
                <TextInput
                    style={styles.searchInput}
                    placeholder="Search titles or niches…"
                    placeholderTextColor={C.muted}
                    value={query}
                    onChangeText={setQuery}
                />
            </View>

            {/* Type filter chips */}
            <View style={styles.chipRow}>
                {types.map(t => (
                    <TouchableOpacity
                        key={t}
                        style={[styles.chip, typeFilter === t && styles.chipActive]}
                        onPress={() => setTypeFilter(t)}
                    >
                        <Text style={[styles.chipText, typeFilter === t && styles.chipTextActive]}>
                            {t}
                        </Text>
                    </TouchableOpacity>
                ))}
            </View>

            {/* Count */}
            <Text style={styles.countText}>{visible.length} products</Text>

            {error ? <Text style={styles.errorText}>{error}</Text> : null}

            <FlatList
                data={visible}
                keyExtractor={item => String(item.id)}
                renderItem={({ item }) => <BookCard item={item} />}
                contentContainerStyle={styles.list}
                refreshControl={
                    <RefreshControl refreshing={loading} onRefresh={load}
                        tintColor={C.blue} colors={[C.blue]} />
                }
                ListEmptyComponent={
                    !loading && (
                        <Text style={styles.emptyText}>
                            {allProducts.length === 0
                                ? 'No products yet — books will appear here once generated.'
                                : 'No results for this filter.'}
                        </Text>
                    )
                }
            />
        </View>
    );
}

const styles = StyleSheet.create({
    container:      { flex: 1, backgroundColor: C.bg },
    searchBar:      { margin: 12, marginBottom: 6 },
    searchInput:    { backgroundColor: C.card, color: C.text, borderRadius: 10,
                      paddingHorizontal: 14, paddingVertical: 10, fontSize: 14,
                      borderWidth: 1, borderColor: C.border },
    chipRow:        { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: 12,
                      gap: 6, marginBottom: 4 },
    chip:           { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 20,
                      backgroundColor: C.card, borderWidth: 1, borderColor: C.border },
    chipActive:     { backgroundColor: C.blue, borderColor: C.blue },
    chipText:       { color: C.muted, fontSize: 12 },
    chipTextActive: { color: '#fff', fontWeight: '600' },
    countText:      { color: C.muted, fontSize: 12, paddingHorizontal: 14, marginBottom: 8 },
    errorText:      { color: '#ef4444', fontSize: 13, margin: 12 },
    list:           { padding: 12, gap: 10, paddingBottom: 40 },
    card:           { backgroundColor: C.card, borderRadius: 12, padding: 14,
                      borderWidth: 1, borderColor: C.border },
    cardTop:        { flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 8 },
    typeBadge:      { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
    typeText:       { fontSize: 11, fontWeight: '600' },
    flag:           { fontSize: 16 },
    price:          { marginLeft: 'auto', color: C.green, fontWeight: '700', fontSize: 15 },
    title:          { color: C.text, fontSize: 15, fontWeight: '600', marginBottom: 4 },
    subtitle:       { color: C.muted, fontSize: 13, marginBottom: 4 },
    niche:          { color: C.blue, fontSize: 11, textTransform: 'capitalize' },
    emptyText:      { color: C.muted, textAlign: 'center', marginTop: 60, fontSize: 14,
                      paddingHorizontal: 30, lineHeight: 22 },
});
