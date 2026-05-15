import React from 'react';
import { NavigationContainer, DefaultTheme } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { StatusBar } from 'expo-status-bar';
import { Ionicons } from '@expo/vector-icons';

import DashboardScreen  from './src/screens/DashboardScreen';
import CatalogueScreen  from './src/screens/CatalogueScreen';
import SettingsScreen   from './src/screens/SettingsScreen';

const Tab = createBottomTabNavigator();

const Theme = {
    ...DefaultTheme,
    colors: {
        ...DefaultTheme.colors,
        background:  '#0f172a',
        card:        '#1e293b',
        text:        '#e2e8f0',
        border:      '#334155',
        notification:'#3b82f6',
    },
};

function tabIcon(route, focused, color, size) {
    const icons = {
        Dashboard: focused ? 'speedometer'   : 'speedometer-outline',
        Catalogue: focused ? 'library'        : 'library-outline',
        Settings:  focused ? 'settings'       : 'settings-outline',
    };
    return <Ionicons name={icons[route.name] || 'ellipse'} size={size} color={color} />;
}

export default function App() {
    return (
        <NavigationContainer theme={Theme}>
            <StatusBar style="light" />
            <Tab.Navigator
                screenOptions={({ route }) => ({
                    tabBarIcon: ({ focused, color, size }) =>
                        tabIcon(route, focused, color, size),
                    tabBarActiveTintColor:   '#3b82f6',
                    tabBarInactiveTintColor: '#64748b',
                    tabBarStyle: {
                        backgroundColor: '#1e293b',
                        borderTopColor:  '#334155',
                    },
                    headerStyle:      { backgroundColor: '#1e293b' },
                    headerTintColor:  '#e2e8f0',
                    headerTitleStyle: { fontWeight: '700' },
                })}
            >
                <Tab.Screen
                    name="Dashboard"
                    component={DashboardScreen}
                    options={{ title: 'Dashboard' }}
                />
                <Tab.Screen
                    name="Catalogue"
                    component={CatalogueScreen}
                    options={{ title: 'Catalogue' }}
                />
                <Tab.Screen
                    name="Settings"
                    component={SettingsScreen}
                    options={{ title: 'Settings' }}
                />
            </Tab.Navigator>
        </NavigationContainer>
    );
}
