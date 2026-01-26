const API_BASE = window.location.origin;
const { createApp, ref, computed, onMounted, watch, onUnmounted } = Vue;

// Auth helper functions
const getStoredTokens = () => {
    try {
        return {
            accessToken: localStorage.getItem('access_token'),
            refreshToken: localStorage.getItem('refresh_token')
        };
    } catch {
        return { accessToken: null, refreshToken: null };
    }
};

const storeTokens = (accessToken, refreshToken) => {
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('refresh_token', refreshToken);
};

const clearTokens = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
};

const parseJwt = (token) => {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        return JSON.parse(window.atob(base64));
    } catch {
        return null;
    }
};

// Get base plan name (strip regional suffix and Local Zone suffix)
const getBasePlanName = (planCode) => {
    // Remove Local Zone suffix first (.LZ, .LZ-eu, .LZ-ca)
    let base = planCode.replace(/\.LZ(-[a-z]+)?$/i, '');
    // Remove regional suffixes like -us, -eu, -ca, -apac
    base = base.replace(/-(us|eu|ca|apac)$/i, '');
    return base;
};

createApp({
    setup() {
        const activeTab = ref('status');
        const loading = ref(true);
        const historyLoading = ref(false);
        const notificationsLoading = ref(false);
        const isRefreshing = ref(false);
        const saving = ref(false);
        const testing = ref(false);
        const deleting = ref(false);
        
        // Auth state
        const isAuthenticated = ref(false);
        const isAdmin = ref(false);
        const currentUser = ref(null);
        const authLoading = ref(false);
        const authError = ref('');
        const showLoginModal = ref(false);
        const showRegisterModal = ref(false);
        const showAddWebhookModal = ref(false);
        const webhookError = ref('');
        const addingWebhook = ref(false);
        
        const loginForm = ref({ email: '', password: '' });
        const registerForm = ref({ email: '', username: '', password: '' });
        const newWebhookForm = ref({ 
            name: '', 
            url: '',
            webhook_type: 'discord',
            slack_channel: '',
            bot_username: '',
            avatar_url: '',
            embed_color: '',
            mention_role_id: '',
            include_price: true,
            include_specs: true
        });
        const webhookColorPicker = ref('#3FB950');
        
        // Password change
        const showChangePasswordModal = ref(false);
        const passwordForm = ref({ current_password: '', new_password: '', confirm_password: '' });
        const passwordError = ref('');
        const passwordSuccess = ref('');
        const changingPassword = ref(false);
        
        // Admin modals and forms
        const showCreateUserModal = ref(false);
        const createUserForm = ref({ email: '', username: '', password: '', is_active: true, is_admin: false });
        const createUserError = ref('');
        const createUserSuccess = ref('');
        const creatingUser = ref(false);
        
        const showCreateGroupModal = ref(false);
        const showEditGroupModal = ref(false);
        const showGroupMembersModal = ref(false);
        const createGroupForm = ref({ name: '', description: '' });
        const editGroupForm = ref({ id: null, name: '', description: '' });
        const groupError = ref('');
        const savingGroup = ref(false);
        
        const selectedGroup = ref(null);
        const groupMembers = ref([]);
        const groupMembersError = ref('');
        const addMemberUserId = ref('');
        const addMemberRole = ref('member');
        const addingMember = ref(false);
        
        // Admin settings
        const allowRegistration = ref(true);
        const adminSettingsMessage = ref('');
        const adminSettingsSuccess = ref(false);
        const availableSubsidiaries = ref([]);
        const selectedSubsidiary = ref('US');
        const subsidiaryUpdating = ref(false);
        
        // Checker settings
        const checkerSettings = ref({
            check_interval_seconds: 120,
            notification_threshold_minutes: 60
        });
        const savingCheckerSettings = ref(false);
        const checkerSettingsMessage = ref('');
        const checkerSettingsSuccess = ref(false);
        
        // Multi-subsidiary state
        const subsidiariesInfo = ref({ active: [], with_data: [], names: {} });
        const activeSubsidiary = ref('US');  // Default to US, or 'ALL' for all
        
        // Subsidiary helper functions
        // FR is used as "Global" for all non-US regions
        const subsidiaryFlags = {
            'US': '🇺🇸',
            'FR': '🌍',  // Global flag for FR (represents all non-US)
        };
        
        const getSubsidiaryFlag = (code) => subsidiaryFlags[code] || '🌐';
        
        const getSubsidiaryName = (code) => {
            return subsidiariesInfo.value.names?.[code] || code;
        };
        
        const getSubsidiaryCount = (code) => {
            return status.value.filter(s => s.subsidiary === code).length;
        };
        
        const subsidiariesWithData = computed(() => {
            return subsidiariesInfo.value.with_data || [];
        });
        
        const setActiveSubsidiary = (code) => {
            activeSubsidiary.value = code;
        };
        
        // User data
        const userWebhooks = ref([]);
        const userSubscriptions = ref([]);
        const userNotifications = ref([]);
        const selectedPlans = ref({});
        const savingSubscriptions = ref(false);
        
        // Admin data
        const adminUsers = ref([]);
        const adminGroups = ref([]);
        const adminLoading = ref(false);
        
        // Comparison data
        const compareData = ref(null);
        const compareFilters = ref({
            search: '',
            show: 'all',
            productLine: '',
            priceWinner: ''
        });
        const showDcBreakdown = ref(false);
        
        const status = ref([]);
        const history = ref([]);
        const notifications = ref([]);
        const plans = ref([]);
        const config = ref({});
        const subsidiary = ref({ code: 'US', name: 'OVHcloud US', domain: 'us.ovhcloud.com', flag: '🇺🇸', region: 'United States' });
        const webhookUrl = ref('');
        const alertMessage = ref('');
        const alertType = ref('success');
        const collapsedPlans = ref({});
        const collapsedGroups = ref({});
        const showInternalPlans = ref(false);  // Internal plans collapsed by default
        const toast = ref({ visible: false, message: '' });
        const selectedDatacenter = ref('');
        
        let refreshInterval = null;

        const filters = ref({
            search: '',
            plan: '',
            datacenter: '',
            status: '',
            region: ''
        });

        const historyFilters = ref({
            plan: '',
            limit: 100
        });

        const pricingModal = ref({
            visible: false,
            loading: false,
            planCode: '',
            tiers: [],
            lastUpdated: ''
        });

        // Auth functions
        const getAuthHeaders = () => {
            const { accessToken } = getStoredTokens();
            return accessToken ? { 'Authorization': `Bearer ${accessToken}` } : {};
        };

        const checkAuth = async () => {
            const { accessToken, refreshToken } = getStoredTokens();
            if (!accessToken) {
                isAuthenticated.value = false;
                isAdmin.value = false;
                currentUser.value = null;
                return;
            }

            const payload = parseJwt(accessToken);
            if (!payload) {
                clearTokens();
                isAuthenticated.value = false;
                return;
            }

            // Check if token is expired
            if (payload.exp * 1000 < Date.now()) {
                // Try to refresh
                if (refreshToken) {
                    try {
                        const response = await fetch(`${API_BASE}/api/auth/refresh`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ refresh_token: refreshToken })
                        });
                        if (response.ok) {
                            const data = await response.json();
                            storeTokens(data.access_token, data.refresh_token);
                            const newPayload = parseJwt(data.access_token);
                            isAuthenticated.value = true;
                            isAdmin.value = newPayload?.is_admin || false;
                            currentUser.value = { email: newPayload?.email };
                            return;
                        }
                    } catch (e) {
                        console.error('Token refresh failed:', e);
                    }
                }
                clearTokens();
                isAuthenticated.value = false;
                return;
            }

            isAuthenticated.value = true;
            isAdmin.value = payload.is_admin || false;
            currentUser.value = { email: payload.email };
        };

        const handleLogin = async () => {
            authError.value = '';
            authLoading.value = true;
            
            try {
                const response = await fetch(`${API_BASE}/api/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(loginForm.value)
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    authError.value = error.detail || 'Login failed';
                    return;
                }
                
                const data = await response.json();
                storeTokens(data.access_token, data.refresh_token);
                await checkAuth();
                showLoginModal.value = false;
                loginForm.value = { email: '', password: '' };
                showToast('Logged in successfully!');
                
                // Fetch user data
                fetchUserData();
            } catch (e) {
                authError.value = 'Network error. Please try again.';
            } finally {
                authLoading.value = false;
            }
        };

        const handleRegister = async () => {
            authError.value = '';
            authLoading.value = true;
            
            try {
                const response = await fetch(`${API_BASE}/api/auth/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(registerForm.value)
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    authError.value = error.detail || 'Registration failed';
                    return;
                }
                
                const data = await response.json();
                storeTokens(data.access_token, data.refresh_token);
                await checkAuth();
                showRegisterModal.value = false;
                registerForm.value = { email: '', username: '', password: '' };
                showToast('Account created successfully!');
                
                // Fetch user data
                fetchUserData();
            } catch (e) {
                authError.value = 'Network error. Please try again.';
            } finally {
                authLoading.value = false;
            }
        };

        const logout = async () => {
            const { refreshToken } = getStoredTokens();
            if (refreshToken) {
                try {
                    await fetch(`${API_BASE}/api/auth/logout`, {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            ...getAuthHeaders()
                        },
                        body: JSON.stringify({ refresh_token: refreshToken })
                    });
                } catch (e) {
                    console.error('Logout API error:', e);
                }
            }
            clearTokens();
            isAuthenticated.value = false;
            isAdmin.value = false;
            currentUser.value = null;
            userWebhooks.value = [];
            userSubscriptions.value = [];
            userNotifications.value = [];
            showToast('Logged out');
        };

        const changePassword = async () => {
            passwordError.value = '';
            passwordSuccess.value = '';
            
            // Validate passwords match
            if (passwordForm.value.new_password !== passwordForm.value.confirm_password) {
                passwordError.value = 'New passwords do not match';
                return;
            }
            
            // Validate password complexity
            const pwd = passwordForm.value.new_password;
            if (pwd.length < 8) {
                passwordError.value = 'Password must be at least 8 characters';
                return;
            }
            if (!/[a-z]/.test(pwd)) {
                passwordError.value = 'Password must contain at least one lowercase letter';
                return;
            }
            if (!/[A-Z]/.test(pwd)) {
                passwordError.value = 'Password must contain at least one uppercase letter';
                return;
            }
            if (!/\d/.test(pwd)) {
                passwordError.value = 'Password must contain at least one digit';
                return;
            }
            if (!/[@$!%*?&^#()_+\-=\[\]{};:'",.<>\\|`~]/.test(pwd)) {
                passwordError.value = 'Password must contain at least one special character';
                return;
            }
            
            changingPassword.value = true;
            
            try {
                const response = await fetch(`${API_BASE}/api/me/password`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({
                        current_password: passwordForm.value.current_password,
                        new_password: passwordForm.value.new_password
                    })
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    passwordError.value = error.detail || 'Failed to change password';
                    return;
                }
                
                passwordSuccess.value = 'Password changed successfully. Please login again.';
                passwordForm.value = { current_password: '', new_password: '', confirm_password: '' };
                
                // Log out after successful password change
                setTimeout(() => {
                    showChangePasswordModal.value = false;
                    logout();
                }, 2000);
            } catch (e) {
                passwordError.value = 'Network error. Please try again.';
            } finally {
                changingPassword.value = false;
            }
        };

        // User data functions
        const fetchUserData = async () => {
            if (!isAuthenticated.value) return;
            
            try {
                const [webhooksRes, subsRes, notifsRes] = await Promise.all([
                    fetch(`${API_BASE}/api/me/webhooks`, { headers: getAuthHeaders() }),
                    fetch(`${API_BASE}/api/me/subscriptions`, { headers: getAuthHeaders() }),
                    fetch(`${API_BASE}/api/me/notifications?limit=50`, { headers: getAuthHeaders() })
                ]);
                
                if (webhooksRes.ok) userWebhooks.value = await webhooksRes.json();
                if (subsRes.ok) {
                    userSubscriptions.value = await subsRes.json();
                    // Initialize selectedPlans from subscriptions
                    selectedPlans.value = {};
                    userSubscriptions.value.forEach(sub => {
                        if (sub.notify_on_available) {
                            selectedPlans.value[sub.plan_code] = true;
                        }
                    });
                }
                if (notifsRes.ok) userNotifications.value = await notifsRes.json();
            } catch (e) {
                console.error('Failed to fetch user data:', e);
            }
        };

        const handleAddWebhook = async () => {
            webhookError.value = '';
            addingWebhook.value = true;
            
            try {
                const payload = {
                    webhook_url: newWebhookForm.value.url,
                    webhook_name: newWebhookForm.value.name,
                    webhook_type: newWebhookForm.value.webhook_type,
                    include_price: newWebhookForm.value.include_price,
                    include_specs: newWebhookForm.value.include_specs
                };
                
                // Add optional fields if provided
                if (newWebhookForm.value.webhook_type === 'slack' && newWebhookForm.value.slack_channel) {
                    payload.slack_channel = newWebhookForm.value.slack_channel;
                }
                if (newWebhookForm.value.webhook_type === 'discord') {
                    if (newWebhookForm.value.bot_username) {
                        payload.bot_username = newWebhookForm.value.bot_username;
                    }
                    if (newWebhookForm.value.avatar_url) {
                        payload.avatar_url = newWebhookForm.value.avatar_url;
                    }
                    if (newWebhookForm.value.embed_color) {
                        payload.embed_color = newWebhookForm.value.embed_color;
                    }
                    if (newWebhookForm.value.mention_role_id) {
                        payload.mention_role_id = newWebhookForm.value.mention_role_id;
                    }
                }
                
                const response = await fetch(`${API_BASE}/api/me/webhooks`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify(payload)
                });
                
                if (!response.ok) {
                    const error = await response.json();
                    webhookError.value = error.detail || 'Failed to add webhook';
                    return;
                }
                
                showAddWebhookModal.value = false;
                newWebhookForm.value = { 
                    name: '', 
                    url: '',
                    webhook_type: 'discord',
                    slack_channel: '',
                    bot_username: '',
                    avatar_url: '',
                    embed_color: '',
                    mention_role_id: '',
                    include_price: true,
                    include_specs: true
                };
                showToast('Webhook added!');
                fetchUserData();
            } catch (e) {
                webhookError.value = 'Network error. Please try again.';
            } finally {
                addingWebhook.value = false;
            }
        };

        const testUserWebhook = async (webhookId) => {
            try {
                const response = await fetch(`${API_BASE}/api/me/webhooks/${webhookId}/test`, {
                    method: 'POST',
                    headers: getAuthHeaders()
                });
                const result = await response.json();
                showToast(result.success ? 'Test notification sent!' : 'Test failed: ' + result.message);
            } catch (e) {
                showToast('Failed to test webhook');
            }
        };

        const toggleUserWebhook = async (wh) => {
            try {
                await fetch(`${API_BASE}/api/me/webhooks/${wh.id}`, {
                    method: 'PUT',
                    headers: { 
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({ is_active: !wh.is_active })
                });
                wh.is_active = !wh.is_active;
                showToast(wh.is_active ? 'Webhook enabled' : 'Webhook disabled');
            } catch (e) {
                showToast('Failed to update webhook');
            }
        };

        const deleteUserWebhook = async (webhookId) => {
            if (!confirm('Delete this webhook?')) return;
            
            try {
                await fetch(`${API_BASE}/api/me/webhooks/${webhookId}`, {
                    method: 'DELETE',
                    headers: getAuthHeaders()
                });
                userWebhooks.value = userWebhooks.value.filter(w => w.id !== webhookId);
                showToast('Webhook deleted');
            } catch (e) {
                showToast('Failed to delete webhook');
            }
        };

        const togglePlanSubscription = (planCode) => {
            selectedPlans.value[planCode] = !selectedPlans.value[planCode];
        };

        const selectAllPlans = () => {
            plans.value.forEach(p => {
                selectedPlans.value[p.plan_code] = true;
            });
        };

        const deselectAllPlans = () => {
            selectedPlans.value = {};
        };

        const saveSubscriptions = async () => {
            savingSubscriptions.value = true;
            
            try {
                // Get list of selected plan codes
                const selectedPlanCodes = Object.keys(selectedPlans.value).filter(k => selectedPlans.value[k]);
                
                await fetch(`${API_BASE}/api/me/subscriptions/bulk`, {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({
                        plan_codes: selectedPlanCodes,
                        notify_on_available: true
                    })
                });
                
                // Remove unselected subscriptions
                const currentSubCodes = userSubscriptions.value.map(s => s.plan_code);
                const toRemove = currentSubCodes.filter(code => !selectedPlans.value[code]);
                
                for (const code of toRemove) {
                    await fetch(`${API_BASE}/api/me/subscriptions/${encodeURIComponent(code)}`, {
                        method: 'DELETE',
                        headers: getAuthHeaders()
                    });
                }
                
                showToast('Subscriptions saved!');
                fetchUserData();
            } catch (e) {
                showToast('Failed to save subscriptions');
            } finally {
                savingSubscriptions.value = false;
            }
        };

        // Admin functions
        const fetchAdminUsers = async () => {
            if (!isAdmin.value) return;
            
            adminLoading.value = true;
            try {
                const response = await fetch(`${API_BASE}/api/admin/users`, {
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    adminUsers.value = await response.json();
                }
            } catch (e) {
                console.error('Failed to fetch users:', e);
            } finally {
                adminLoading.value = false;
            }
        };

        const toggleUserActive = async (user) => {
            try {
                const response = await fetch(`${API_BASE}/api/admin/users/${user.id}?is_active=${!user.is_active}`, {
                    method: 'PUT',
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    user.is_active = !user.is_active;
                    showToast(`User ${user.is_active ? 'enabled' : 'disabled'}`);
                } else {
                    const err = await response.json();
                    showToast(err.detail || 'Failed to update user');
                }
            } catch (e) {
                showToast('Failed to update user');
            }
        };

        const toggleUserAdmin = async (user) => {
            const action = user.is_admin ? 'remove admin from' : 'make admin';
            if (!confirm(`Are you sure you want to ${action} ${user.email}?`)) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/users/${user.id}?is_admin=${!user.is_admin}`, {
                    method: 'PUT',
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    user.is_admin = !user.is_admin;
                    showToast(`User is now ${user.is_admin ? 'an admin' : 'a regular user'}`);
                } else {
                    const err = await response.json();
                    showToast(err.detail || 'Failed to update user');
                }
            } catch (e) {
                showToast('Failed to update user');
            }
        };

        const confirmDeleteUser = async (user) => {
            if (!confirm(`Are you sure you want to DELETE ${user.email}? This cannot be undone.`)) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/users/${user.id}`, {
                    method: 'DELETE',
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    adminUsers.value = adminUsers.value.filter(u => u.id !== user.id);
                    showToast('User deleted');
                } else {
                    const err = await response.json();
                    showToast(err.detail || 'Failed to delete user');
                }
            } catch (e) {
                showToast('Failed to delete user');
            }
        };

        // Admin Create User
        const handleCreateUser = async () => {
            createUserError.value = '';
            createUserSuccess.value = '';
            
            if (!createUserForm.value.email || !createUserForm.value.username || !createUserForm.value.password) {
                createUserError.value = 'Email, username, and password are required';
                return;
            }
            
            if (createUserForm.value.password.length < 8) {
                createUserError.value = 'Password must be at least 8 characters';
                return;
            }
            
            creatingUser.value = true;
            try {
                const response = await fetch(`${API_BASE}/api/admin/users`, {
                    method: 'POST',
                    headers: {
                        ...getAuthHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(createUserForm.value)
                });
                
                if (response.ok) {
                    createUserSuccess.value = 'User created successfully!';
                    createUserForm.value = { email: '', username: '', password: '', is_active: true, is_admin: false };
                    await fetchAdminUsers();
                    setTimeout(() => {
                        showCreateUserModal.value = false;
                        createUserSuccess.value = '';
                    }, 1500);
                } else {
                    const err = await response.json();
                    createUserError.value = err.detail || 'Failed to create user';
                }
            } catch (e) {
                createUserError.value = 'Failed to create user';
            } finally {
                creatingUser.value = false;
            }
        };

        // Admin Registration Toggle
        const fetchRegistrationSetting = async () => {
            if (!isAdmin.value) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/settings/registration`, {
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    const data = await response.json();
                    allowRegistration.value = data.allow_registration;
                }
            } catch (e) {
                console.error('Failed to fetch registration setting:', e);
            }
        };

        const toggleRegistration = async () => {
            adminSettingsMessage.value = '';
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/settings/registration`, {
                    method: 'PUT',
                    headers: {
                        ...getAuthHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ allow_registration: allowRegistration.value })
                });
                
                if (response.ok) {
                    adminSettingsMessage.value = `Public registration ${allowRegistration.value ? 'enabled' : 'disabled'}`;
                    adminSettingsSuccess.value = true;
                    setTimeout(() => { adminSettingsMessage.value = ''; }, 3000);
                } else {
                    const err = await response.json();
                    adminSettingsMessage.value = err.detail || 'Failed to update setting';
                    adminSettingsSuccess.value = false;
                    // Revert the checkbox
                    allowRegistration.value = !allowRegistration.value;
                }
            } catch (e) {
                adminSettingsMessage.value = 'Failed to update setting';
                adminSettingsSuccess.value = false;
                allowRegistration.value = !allowRegistration.value;
            }
        };

        // Checker Settings
        const fetchCheckerSettings = async () => {
            if (!isAdmin.value) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/settings/checker`, {
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    const data = await response.json();
                    checkerSettings.value = data;
                }
            } catch (e) {
                console.error('Failed to fetch checker settings:', e);
            }
        };

        const saveCheckerSettings = async () => {
            checkerSettingsMessage.value = '';
            savingCheckerSettings.value = true;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/settings/checker`, {
                    method: 'PUT',
                    headers: {
                        ...getAuthHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(checkerSettings.value)
                });
                
                if (response.ok) {
                    const data = await response.json();
                    checkerSettings.value = data;
                    checkerSettingsMessage.value = 'Checker settings saved! Agents will use new values on next cycle.';
                    checkerSettingsSuccess.value = true;
                    setTimeout(() => { checkerSettingsMessage.value = ''; }, 5000);
                } else {
                    const err = await response.json();
                    checkerSettingsMessage.value = err.detail || 'Failed to save settings';
                    checkerSettingsSuccess.value = false;
                }
            } catch (e) {
                checkerSettingsMessage.value = 'Failed to save settings';
                checkerSettingsSuccess.value = false;
            } finally {
                savingCheckerSettings.value = false;
            }
        };

        // Subsidiary Management
        const fetchAvailableSubsidiaries = async () => {
            try {
                // Fetch subsidiaries with data for the tabs
                const response = await fetch(`${API_BASE}/api/subsidiaries`);
                if (response.ok) {
                    const data = await response.json();
                    subsidiariesInfo.value = data;
                    
                    // Set default subsidiary: prefer US if it has data, otherwise first available
                    if (data.with_data && data.with_data.length > 0) {
                        if (data.with_data.includes('US')) {
                            activeSubsidiary.value = 'US';
                        } else {
                            activeSubsidiary.value = data.with_data[0];
                        }
                    }
                }
                
                // Fetch all subsidiaries for admin dropdown
                const allResponse = await fetch(`${API_BASE}/api/subsidiaries/all`);
                if (allResponse.ok) {
                    availableSubsidiaries.value = await allResponse.json();
                }
            } catch (e) {
                console.error('Failed to fetch subsidiaries:', e);
            }
        };

        const updateSubsidiary = async () => {
            adminSettingsMessage.value = '';
            subsidiaryUpdating.value = true;
            
            try {
                const response = await fetch(`${API_BASE}/api/config/subsidiary`, {
                    method: 'PUT',
                    headers: {
                        ...getAuthHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ code: selectedSubsidiary.value })
                });
                
                if (response.ok) {
                    const data = await response.json();
                    subsidiary.value = data.subsidiary;
                    adminSettingsMessage.value = `Subsidiary updated to ${data.subsidiary.name}. Restart the checker to fetch new catalog data.`;
                    adminSettingsSuccess.value = true;
                    setTimeout(() => { adminSettingsMessage.value = ''; }, 5000);
                } else {
                    const err = await response.json();
                    adminSettingsMessage.value = err.detail || 'Failed to update subsidiary';
                    adminSettingsSuccess.value = false;
                }
            } catch (e) {
                adminSettingsMessage.value = 'Failed to update subsidiary';
                adminSettingsSuccess.value = false;
            } finally {
                subsidiaryUpdating.value = false;
            }
        };

        // Admin Group Management
        const fetchAdminGroups = async () => {
            if (!isAdmin.value) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/groups`, {
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    adminGroups.value = await response.json();
                }
            } catch (e) {
                console.error('Failed to fetch groups:', e);
            }
        };

        const handleCreateGroup = async () => {
            groupError.value = '';
            
            if (!createGroupForm.value.name) {
                groupError.value = 'Group name is required';
                return;
            }
            
            savingGroup.value = true;
            try {
                const response = await fetch(`${API_BASE}/api/admin/groups`, {
                    method: 'POST',
                    headers: {
                        ...getAuthHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(createGroupForm.value)
                });
                
                if (response.ok) {
                    showToast('Group created');
                    createGroupForm.value = { name: '', description: '' };
                    showCreateGroupModal.value = false;
                    await fetchAdminGroups();
                } else {
                    const err = await response.json();
                    groupError.value = err.detail || 'Failed to create group';
                }
            } catch (e) {
                groupError.value = 'Failed to create group';
            } finally {
                savingGroup.value = false;
            }
        };

        const editGroup = (group) => {
            editGroupForm.value = { id: group.id, name: group.name, description: group.description || '' };
            groupError.value = '';
            showEditGroupModal.value = true;
        };

        const handleUpdateGroup = async () => {
            groupError.value = '';
            
            if (!editGroupForm.value.name) {
                groupError.value = 'Group name is required';
                return;
            }
            
            savingGroup.value = true;
            try {
                const response = await fetch(`${API_BASE}/api/admin/groups/${editGroupForm.value.id}`, {
                    method: 'PUT',
                    headers: {
                        ...getAuthHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        name: editGroupForm.value.name,
                        description: editGroupForm.value.description
                    })
                });
                
                if (response.ok) {
                    showToast('Group updated');
                    showEditGroupModal.value = false;
                    await fetchAdminGroups();
                } else {
                    const err = await response.json();
                    groupError.value = err.detail || 'Failed to update group';
                }
            } catch (e) {
                groupError.value = 'Failed to update group';
            } finally {
                savingGroup.value = false;
            }
        };

        const confirmDeleteGroup = async (group) => {
            if (!confirm(`Are you sure you want to delete the group "${group.name}"? This cannot be undone.`)) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/groups/${group.id}`, {
                    method: 'DELETE',
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    adminGroups.value = adminGroups.value.filter(g => g.id !== group.id);
                    showToast('Group deleted');
                } else {
                    const err = await response.json();
                    showToast(err.detail || 'Failed to delete group');
                }
            } catch (e) {
                showToast('Failed to delete group');
            }
        };

        // Group Members Management
        const showGroupMembers = async (group) => {
            selectedGroup.value = group;
            groupMembersError.value = '';
            addMemberUserId.value = '';
            addMemberRole.value = 'member';
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/groups/${group.id}/members`, {
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    groupMembers.value = await response.json();
                } else {
                    groupMembers.value = [];
                }
            } catch (e) {
                groupMembers.value = [];
                console.error('Failed to fetch group members:', e);
            }
            
            showGroupMembersModal.value = true;
        };

        const availableUsersForGroup = computed(() => {
            const memberIds = new Set(groupMembers.value.map(m => m.user_id));
            return adminUsers.value.filter(u => !memberIds.has(u.id));
        });

        const handleAddGroupMember = async () => {
            if (!addMemberUserId.value || !selectedGroup.value) return;
            
            groupMembersError.value = '';
            addingMember.value = true;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/groups/${selectedGroup.value.id}/members`, {
                    method: 'POST',
                    headers: {
                        ...getAuthHeaders(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        user_id: parseInt(addMemberUserId.value),
                        role: addMemberRole.value
                    })
                });
                
                if (response.ok) {
                    showToast('Member added');
                    addMemberUserId.value = '';
                    addMemberRole.value = 'member';
                    // Refresh members list
                    await showGroupMembers(selectedGroup.value);
                    await fetchAdminGroups(); // Update member count
                } else {
                    const err = await response.json();
                    groupMembersError.value = err.detail || 'Failed to add member';
                }
            } catch (e) {
                groupMembersError.value = 'Failed to add member';
            } finally {
                addingMember.value = false;
            }
        };

        const handleRemoveGroupMember = async (member) => {
            if (!confirm(`Remove ${member.username} from this group?`)) return;
            
            try {
                const response = await fetch(`${API_BASE}/api/admin/groups/${selectedGroup.value.id}/members/${member.user_id}`, {
                    method: 'DELETE',
                    headers: getAuthHeaders()
                });
                
                if (response.ok) {
                    groupMembers.value = groupMembers.value.filter(m => m.user_id !== member.user_id);
                    showToast('Member removed');
                    await fetchAdminGroups(); // Update member count
                } else {
                    const err = await response.json();
                    showToast(err.detail || 'Failed to remove member');
                }
            } catch (e) {
                showToast('Failed to remove member');
            }
        };

        // All plans for subscription selection
        const allPlansForSubscription = computed(() => {
            return plans.value.filter(p => p.enabled);
        });

        // Computed
        const availablePlans = computed(() => {
            const planSet = new Set(status.value.map(s => s.plan_code));
            return Array.from(planSet).sort();
        });

        const availableDatacenters = computed(() => {
            const dcSet = new Set(status.value.map(s => s.datacenter));
            return Array.from(dcSet).sort();
        });

        const totalPlans = computed(() => availablePlans.value.length);
        const totalDatacenters = computed(() => availableDatacenters.value.length);

        // Use location_region from API, fallback to guessing
        const getRegion = (item) => {
            if (item.location_region) return item.location_region;
            // Fallback for items without location data
            const dc = item.datacenter.toUpperCase();
            if (dc.includes('US-')) return 'US';
            if (dc.includes('CA-') || dc.includes('BHS')) return 'CA';
            if (dc.includes('EU-') || dc.includes('GRA') || dc.includes('SBG')) return 'EU';
            if (dc.includes('AP-') || dc.includes('SYD') || dc.includes('SG')) return 'APAC';
            return 'OTHER';
        };

        // Filtered comparison data
        const filteredCompareData = computed(() => {
            if (!compareData.value?.comparisons) return [];
            
            return compareData.value.comparisons.filter(item => {
                // Search filter
                if (compareFilters.value.search) {
                    const search = compareFilters.value.search.toLowerCase();
                    if (!item.base_plan.toLowerCase().includes(search) &&
                        !(item.display_name || '').toLowerCase().includes(search)) {
                        return false;
                    }
                }
                
                // Show filter
                switch (compareFilters.value.show) {
                    case 'both':
                        if (!item.us || !item.global) return false;
                        break;
                    case 'us-only':
                        if (!item.us || item.global) return false;
                        break;
                    case 'global-only':
                        if (item.us || !item.global) return false;
                        break;
                    case 'price-diff':
                        if (!item.us || !item.global) return false;
                        // Only show if both have prices
                        if (!item.us.price_microcents || !item.global.price_microcents) return false;
                        break;
                }
                
                // Product line filter
                if (compareFilters.value.productLine) {
                    if (item.product_line !== compareFilters.value.productLine) return false;
                }
                
                // Price winner filter
                if (compareFilters.value.priceWinner) {
                    const winner = item.price_comparison?.cheaper_region;
                    switch (compareFilters.value.priceWinner) {
                        case 'us':
                            if (winner !== 'US') return false;
                            break;
                        case 'global':
                            if (winner !== 'Global') return false;
                            break;
                        case 'same':
                            if (winner !== null || !item.price_comparison) return false;
                            break;
                    }
                }
                
                return true;
            });
        });

        const filteredStatus = computed(() => {
            return status.value.filter(item => {
                // Filter by active subsidiary first
                if (activeSubsidiary.value !== 'ALL' && item.subsidiary !== activeSubsidiary.value) {
                    return false;
                }
                if (filters.value.search) {
                    const search = filters.value.search.toLowerCase();
                    if (!item.plan_code.toLowerCase().includes(search) && 
                        !item.datacenter.toLowerCase().includes(search) &&
                        !(item.display_name || '').toLowerCase().includes(search) &&
                        !(item.location_city || '').toLowerCase().includes(search) &&
                        !(item.location_country || '').toLowerCase().includes(search)) {
                        return false;
                    }
                }
                if (filters.value.plan && item.plan_code !== filters.value.plan) return false;
                if (filters.value.datacenter && item.datacenter !== filters.value.datacenter) return false;
                if (filters.value.status === 'available' && !item.is_available) return false;
                if (filters.value.status === 'unavailable' && item.is_available) return false;
                if (filters.value.region && getRegion(item) !== filters.value.region) return false;
                return true;
            });
        });

        const filteredGroupedStatus = computed(() => {
            const groups = {};
            for (const item of filteredStatus.value) {
                const basePlan = getBasePlanName(item.plan_code);
                if (!groups[basePlan]) {
                    // Get base display name (strip regional suffixes from display name)
                    let baseDisplayName = (item.display_name || item.plan_code)
                        .replace(/\s*\((Canada|EU|Local Zone|EU Local Zone|US)\)\s*/gi, '')
                        .trim();
                    
                    groups[basePlan] = {
                        base_plan: basePlan,
                        display_name: baseDisplayName,
                        purchase_url: item.purchase_url,
                        price: item.price,
                        specs: item.specs,
                        vcpu: item.vcpu,
                        ram_gb: item.ram_gb,
                        storage_gb: item.storage_gb,
                        storage_type: item.storage_type,
                        bandwidth_mbps: item.bandwidth_mbps,
                        is_orderable: item.is_orderable !== false,
                        datacenters: [],
                        datacenterSet: new Set(),  // Track seen datacenters to avoid duplicates
                        available_count: 0,
                        unavailable_count: 0
                    };
                }
                
                // Add datacenter only if not already seen (dedupe across regional variants)
                if (!groups[basePlan].datacenterSet.has(item.datacenter)) {
                    groups[basePlan].datacenterSet.add(item.datacenter);
                    groups[basePlan].datacenters.push(item);
                    
                    if (item.is_available) {
                        groups[basePlan].available_count++;
                    } else {
                        groups[basePlan].unavailable_count++;
                    }
                }
                
                // Update specs if we don't have them yet
                if (!groups[basePlan].specs && item.specs) {
                    groups[basePlan].specs = item.specs;
                    groups[basePlan].vcpu = item.vcpu;
                    groups[basePlan].ram_gb = item.ram_gb;
                    groups[basePlan].storage_gb = item.storage_gb;
                    groups[basePlan].storage_type = item.storage_type;
                    groups[basePlan].bandwidth_mbps = item.bandwidth_mbps;
                }
            }
            return groups;
        });

        // Split into orderable and internal plans
        const orderablePlans = computed(() => {
            const result = {};
            for (const [key, group] of Object.entries(filteredGroupedStatus.value)) {
                if (group.is_orderable) {
                    result[key] = group;
                }
            }
            return result;
        });

        const internalPlans = computed(() => {
            const result = {};
            for (const [key, group] of Object.entries(filteredGroupedStatus.value)) {
                if (!group.is_orderable) {
                    result[key] = group;
                }
            }
            return result;
        });

        const stats = computed(() => {
            const filtered = filteredStatus.value;
            return {
                available: filtered.filter(s => s.is_available).length,
                outOfStock: filtered.filter(s => !s.is_available).length,
                plans: Object.keys(filteredGroupedStatus.value).length,
                orderablePlans: Object.keys(orderablePlans.value).length,
                internalPlans: Object.keys(internalPlans.value).length,
                datacenters: new Set(filtered.map(s => s.datacenter)).size
            };
        });

        const hasActiveFilters = computed(() => {
            return filters.value.search || filters.value.plan || filters.value.datacenter || 
                   filters.value.status || filters.value.region;
        });

        const allOrderableCollapsed = computed(() => {
            const keys = Object.keys(orderablePlans.value);
            if (keys.length === 0) return false;
            return keys.every(k => collapsedPlans.value[k]);
        });

        const allInternalCollapsed = computed(() => {
            const keys = Object.keys(internalPlans.value);
            if (keys.length === 0) return false;
            return keys.every(k => collapsedPlans.value[k]);
        });

        // Datacenter view - plans for a specific datacenter
        const datacenterPlans = computed(() => {
            if (!selectedDatacenter.value) return [];
            return status.value
                .filter(item => item.datacenter === selectedDatacenter.value)
                .map(item => ({
                    ...item,
                    base_plan: getBasePlanName(item.plan_code),
                    display_name_clean: (item.display_name || item.plan_code)
                        .replace(/\s*\((Canada|EU|Local Zone|EU Local Zone|US)\)\s*/gi, '').trim()
                }))
                .sort((a, b) => {
                    // Sort by display name or plan code
                    const aName = a.display_name_clean || a.plan_code;
                    const bName = b.display_name_clean || b.plan_code;
                    return aName.localeCompare(bName, undefined, { numeric: true });
                });
        });

        const datacenterInfo = computed(() => {
            if (!selectedDatacenter.value || datacenterPlans.value.length === 0) return null;
            const sample = datacenterPlans.value[0];
            return {
                datacenter: selectedDatacenter.value,
                location_city: sample.location_city,
                location_country: sample.location_country,
                location_flag: sample.location_flag,
                total: datacenterPlans.value.length,
                available: datacenterPlans.value.filter(p => p.is_available).length,
                unavailable: datacenterPlans.value.filter(p => !p.is_available).length
            };
        });

        // URL handling
        const parseHash = () => {
            const hash = window.location.hash.slice(1) || '/status';
            const [path, queryString] = hash.split('?');
            const tab = path.replace('/', '') || 'status';
            
            activeTab.value = ['status', 'compare', 'datacenter', 'history', 'notifications', 'settings', 'my-alerts', 'admin', 'profile'].includes(tab) ? tab : 'status';
            
            // Fetch comparison data when switching to compare tab
            if (tab === 'compare' && !compareData.value) {
                fetchCompareData();
            }
            
            if (queryString) {
                const params = new URLSearchParams(queryString);
                filters.value.search = params.get('search') || '';
                filters.value.plan = params.get('plan') || '';
                filters.value.datacenter = params.get('datacenter') || '';
                filters.value.status = params.get('status') || '';
                filters.value.region = params.get('region') || '';
                // Handle datacenter tab selection
                if (tab === 'datacenter' && params.get('dc')) {
                    selectedDatacenter.value = params.get('dc');
                }
            }
        };

        const updateUrl = () => {
            const params = new URLSearchParams();
            if (filters.value.search) params.set('search', filters.value.search);
            if (filters.value.plan) params.set('plan', filters.value.plan);
            if (filters.value.datacenter) params.set('datacenter', filters.value.datacenter);
            if (filters.value.status) params.set('status', filters.value.status);
            if (filters.value.region) params.set('region', filters.value.region);
            
            const query = params.toString();
            const newHash = `#/${activeTab.value}${query ? '?' + query : ''}`;
            
            if (window.location.hash !== newHash) {
                window.history.replaceState(null, '', newHash);
            }
        };

        const copyPermalink = async () => {
            updateUrl();
            try {
                await navigator.clipboard.writeText(window.location.href);
                showToast('Link copied!');
            } catch (err) {
                showToast('Failed to copy link');
            }
        };

        const showToast = (message) => {
            toast.value = { visible: true, message };
            setTimeout(() => toast.value.visible = false, 2500);
        };

        const clearFilters = () => {
            filters.value = { search: '', plan: '', datacenter: '', status: '', region: '' };
            updateUrl();
        };

        const filterByDatacenter = (dc) => {
            filters.value.datacenter = filters.value.datacenter === dc ? '' : dc;
            updateUrl();
        };

        const togglePlanCollapse = (planCode) => {
            collapsedPlans.value[planCode] = !collapsedPlans.value[planCode];
        };

        const toggleGroupCollapse = (basePlan) => {
            collapsedGroups.value[basePlan] = !collapsedGroups.value[basePlan];
        };

        const toggleCollapseAll = (section) => {
            const plans = section === 'orderable' ? orderablePlans.value : internalPlans.value;
            const keys = Object.keys(plans);
            const allCollapsed = section === 'orderable' ? allOrderableCollapsed.value : allInternalCollapsed.value;
            keys.forEach(k => {
                collapsedPlans.value[k] = !allCollapsed;
            });
        };

        const selectDatacenter = (dc) => {
            selectedDatacenter.value = dc;
            activeTab.value = 'datacenter';
            window.location.hash = `#/datacenter?dc=${encodeURIComponent(dc)}`;
        };

        const formatBasePlanName = (basePlan) => {
            // Convert vps-2025-model1 to "VPS Model 1" etc.
            const match = basePlan.match(/vps-(\d+)-model(\d+)(\.LZ)?/i);
            if (match) {
                const year = match[1];
                const model = match[2];
                const lz = match[3] ? ' (Local Zone)' : '';
                const names = {
                    '1': 'Starter',
                    '2': 'Value',
                    '3': 'Essential',
                    '4': 'Comfort',
                    '5': 'Elite',
                    '6': 'Premium'
                };
                return `VPS ${names[model] || 'Model ' + model}${lz}`;
            }
            return basePlan;
        };

        const showAlert = (message, type = 'success') => {
            alertMessage.value = message;
            alertType.value = type;
            setTimeout(() => alertMessage.value = '', 5000);
        };

        const formatDate = (dateStr) => {
            if (!dateStr) return '—';
            return new Date(dateStr).toLocaleString();
        };

        const formatDuration = (minutes) => {
            if (minutes < 60) return `${Math.round(minutes)}m`;
            if (minutes < 1440) return `${Math.round(minutes / 60)}h`;
            return `${Math.round(minutes / 1440)}d`;
        };

        // API calls - only update data, don't refresh entire page
        const fetchStatus = async (showIndicator = false) => {
            try {
                if (showIndicator) isRefreshing.value = true;
                const response = await fetch(`${API_BASE}/api/status`);
                status.value = await response.json();
            } catch (error) {
                console.error('Failed to fetch status:', error);
            } finally {
                loading.value = false;
                isRefreshing.value = false;
            }
        };

        const fetchCompareData = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/compare`);
                if (response.ok) {
                    compareData.value = await response.json();
                }
            } catch (error) {
                console.error('Failed to fetch comparison data:', error);
            }
        };

        const fetchHistory = async () => {
            if (!isAuthenticated.value) return;
            try {
                historyLoading.value = true;
                let url = `${API_BASE}/api/status/history?limit=${historyFilters.value.limit}`;
                if (historyFilters.value.plan) url += `&plan_code=${encodeURIComponent(historyFilters.value.plan)}`;
                const response = await fetch(url, {
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    history.value = await response.json();
                }
            } catch (error) {
                console.error('Failed to fetch history:', error);
            } finally {
                historyLoading.value = false;
            }
        };

        const fetchNotifications = async () => {
            if (!isAuthenticated.value) return;
            try {
                notificationsLoading.value = true;
                const response = await fetch(`${API_BASE}/api/notifications`, {
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    notifications.value = await response.json();
                }
            } catch (error) {
                console.error('Failed to fetch notifications:', error);
            } finally {
                notificationsLoading.value = false;
            }
        };

        const fetchPlans = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/plans`);
                plans.value = await response.json();
            } catch (error) {
                console.error('Failed to fetch plans:', error);
            }
        };

        const fetchSubsidiary = async () => {
            try {
                const response = await fetch(`${API_BASE}/api/subsidiary`);
                if (response.ok) {
                    subsidiary.value = await response.json();
                }
            } catch (error) {
                console.error('Failed to fetch subsidiary info:', error);
            }
        };

        const fetchConfig = async () => {
            if (!isAdmin.value) return;
            try {
                const response = await fetch(`${API_BASE}/api/config`, {
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    config.value = await response.json();
                }
            } catch (error) {
                console.error('Failed to fetch config:', error);
            }
        };

        const saveWebhook = async () => {
            if (!webhookUrl.value) {
                showAlert('Please enter a webhook URL', 'danger');
                return;
            }
            try {
                saving.value = true;
                const response = await fetch(`${API_BASE}/api/config/discord-webhook`, {
                    method: 'PUT',
                    headers: { 
                        'Content-Type': 'application/json',
                        ...getAuthHeaders()
                    },
                    body: JSON.stringify({ webhook_url: webhookUrl.value })
                });
                if (response.ok) {
                    showAlert('Webhook saved!', 'success');
                    webhookUrl.value = '';
                    await fetchConfig();
                } else {
                    const error = await response.json();
                    showAlert(error.detail || 'Failed to save', 'danger');
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'danger');
            } finally {
                saving.value = false;
            }
        };

        const testWebhook = async () => {
            try {
                testing.value = true;
                const response = await fetch(`${API_BASE}/api/config/discord-webhook/test`, { 
                    method: 'POST',
                    headers: getAuthHeaders()
                });
                const result = await response.json();
                showAlert(result.success ? 'Test sent!' : 'Test failed: ' + result.message, 
                          result.success ? 'success' : 'danger');
                await fetchNotifications();
            } catch (error) {
                showAlert('Error: ' + error.message, 'danger');
            } finally {
                testing.value = false;
            }
        };

        const deleteWebhook = async () => {
            if (!confirm('Are you sure you want to delete the default webhook?')) {
                return;
            }
            try {
                deleting.value = true;
                const response = await fetch(`${API_BASE}/api/config/discord-webhook`, {
                    method: 'DELETE',
                    headers: getAuthHeaders()
                });
                if (response.ok) {
                    showAlert('Webhook deleted!', 'success');
                    await fetchConfig();
                } else {
                    const error = await response.json();
                    showAlert(error.detail || 'Failed to delete', 'danger');
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'danger');
            } finally {
                deleting.value = false;
            }
        };

        const togglePlanEnabled = async (plan) => {
            try {
                const response = await fetch(`${API_BASE}/api/plans/${encodeURIComponent(plan.plan_code)}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ enabled: !plan.enabled })
                });
                if (response.ok) {
                    plan.enabled = !plan.enabled;
                    showToast(`Plan ${plan.enabled ? 'enabled' : 'disabled'}`);
                }
            } catch (error) {
                showAlert('Error: ' + error.message, 'danger');
            }
        };

        const showPricing = async (planCode) => {
            pricingModal.value = { visible: true, loading: true, planCode, tiers: [], lastUpdated: '' };
            
            try {
                const [tiersRes, infoRes] = await Promise.all([
                    fetch(`${API_BASE}/api/pricing/${encodeURIComponent(planCode)}`),
                    fetch(`${API_BASE}/api/pricing`)
                ]);
                pricingModal.value.tiers = await tiersRes.json();
                const info = await infoRes.json();
                pricingModal.value.lastUpdated = info.last_updated ? new Date(info.last_updated).toLocaleString() : 'Unknown';
            } catch (error) {
                console.error('Failed to fetch pricing:', error);
            } finally {
                pricingModal.value.loading = false;
            }
        };

        // Watch tab changes
        watch(activeTab, (newTab) => {
            updateUrl();
            if (newTab === 'history' && history.value.length === 0) fetchHistory();
            if (newTab === 'notifications' && notifications.value.length === 0) fetchNotifications();
            if (newTab === 'settings' && plans.value.length === 0) {
                fetchPlans();
                fetchConfig();
            }
            if (newTab === 'my-alerts' && isAuthenticated.value) {
                fetchUserData();
                if (plans.value.length === 0) fetchPlans();
            }
            if (newTab === 'admin' && isAdmin.value) {
                fetchAdminUsers();
                fetchAdminGroups();
                fetchRegistrationSetting();
                fetchCheckerSettings();
                fetchAvailableSubsidiaries();
                // Set selected subsidiary from current config
                selectedSubsidiary.value = subsidiary.value.code;
            }
        });

        // Initialize
        onMounted(async () => {
            // Check authentication first
            await checkAuth();
            
            // Fetch subsidiary info (multi-subsidiary data)
            await fetchAvailableSubsidiaries();
            fetchSubsidiary();
            
            parseHash();
            
            // Initial data load
            fetchStatus();
            
            // Load user data if authenticated
            if (isAuthenticated.value) {
                fetchUserData();
            }
            
            // Background refresh every 30 seconds - only updates data, not page
            refreshInterval = setInterval(() => {
                fetchStatus(true);
            }, 30000);
            
            window.addEventListener('hashchange', parseHash);
        });

        onUnmounted(() => {
            if (refreshInterval) clearInterval(refreshInterval);
            window.removeEventListener('hashchange', parseHash);
        });

        return {
            activeTab, loading, historyLoading, notificationsLoading, isRefreshing,
            saving, testing, status, history, notifications, plans, config, webhookUrl,
            alertMessage, alertType, collapsedPlans, collapsedGroups, showInternalPlans, filters, historyFilters, 
            pricingModal, toast, availablePlans, availableDatacenters, totalPlans, 
            totalDatacenters, filteredGroupedStatus, orderablePlans, internalPlans, stats, hasActiveFilters,
            allOrderableCollapsed, allInternalCollapsed, selectedDatacenter, datacenterPlans, datacenterInfo,
            subsidiary,
            // Multi-subsidiary support
            subsidiariesInfo, activeSubsidiary, subsidiariesWithData,
            getSubsidiaryFlag, getSubsidiaryName, getSubsidiaryCount, setActiveSubsidiary,
            // Comparison feature
            compareData, compareFilters, filteredCompareData, showDcBreakdown, fetchCompareData,
            formatDate, formatDuration, formatBasePlanName, saveWebhook, testWebhook, deleteWebhook, deleting, togglePlanEnabled,
            showPricing, updateUrl, copyPermalink, clearFilters, filterByDatacenter, 
            togglePlanCollapse, toggleGroupCollapse, toggleCollapseAll, selectDatacenter, fetchHistory, showAlert,
            // Auth
            isAuthenticated, isAdmin, currentUser, authLoading, authError,
            showLoginModal, showRegisterModal, loginForm, registerForm,
            handleLogin, handleRegister, logout,
            // User data
            userWebhooks, userSubscriptions, userNotifications, selectedPlans, savingSubscriptions,
            showAddWebhookModal, webhookError, addingWebhook, newWebhookForm, webhookColorPicker,
            handleAddWebhook, testUserWebhook, toggleUserWebhook, deleteUserWebhook,
            togglePlanSubscription, selectAllPlans, deselectAllPlans, saveSubscriptions,
            allPlansForSubscription,
            // Password change
            showChangePasswordModal, passwordForm, passwordError, passwordSuccess, changingPassword,
            changePassword,
            // Admin data
            adminUsers, adminGroups, adminLoading, fetchAdminUsers, fetchAdminGroups,
            toggleUserActive, toggleUserAdmin, confirmDeleteUser,
            // Admin user creation
            showCreateUserModal, createUserForm, createUserError, createUserSuccess, creatingUser,
            handleCreateUser,
            // Admin settings
            allowRegistration, adminSettingsMessage, adminSettingsSuccess,
            fetchRegistrationSetting, toggleRegistration,
            availableSubsidiaries, selectedSubsidiary, subsidiaryUpdating,
            fetchAvailableSubsidiaries, updateSubsidiary,
            // Checker settings
            checkerSettings, savingCheckerSettings, checkerSettingsMessage, checkerSettingsSuccess,
            fetchCheckerSettings, saveCheckerSettings,
            // Admin group management
            showCreateGroupModal, showEditGroupModal, showGroupMembersModal,
            createGroupForm, editGroupForm, groupError, savingGroup,
            handleCreateGroup, editGroup, handleUpdateGroup, confirmDeleteGroup,
            // Group members
            selectedGroup, groupMembers, groupMembersError, addMemberUserId, addMemberRole, addingMember,
            availableUsersForGroup, showGroupMembers, handleAddGroupMember, handleRemoveGroupMember
        };
    }
}).mount('#app');
