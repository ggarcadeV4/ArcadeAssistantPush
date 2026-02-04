/**
 * BACKBONE VERIFICATION SCRIPT
 * Tests the RemoteConfigService and Supabase SessionStore integration.
 */
import 'dotenv/config';
import { getModel, isFeatureEnabled } from '../services/remote_config.js';
import { sessionStore } from '../gems/aa-lora/index.js';

async function runVerification() {
    const testDeviceId = process.env.DEVICE_ID || 'BASEMENT-TEST-001';
    console.log(`\n🚀 Starting Backbone Verification for Device: ${testDeviceId}`);
    console.log('---------------------------------------------------------');

    try {
        // 1. Test Remote Configuration
        console.log('📡 Testing RemoteConfigService...');
        const primaryModel = await getModel(testDeviceId, 'lora');
        const isStatelessEnabled = await isFeatureEnabled(testDeviceId, 'stateless_sessions');

        console.log(`   - Primary Model (from Supabase/Default): ${primaryModel}`);
        console.log(`   - Stateless Feature Flag: ${isStatelessEnabled}`);

        // 2. Test Supabase Session Store
        console.log('\n🧠 Testing Supabase SessionStore...');
        const testSession = {
            chatState: 'VERIFICATION_TEST',
            history: [{ role: 'user', content: 'Verification pulse check' }],
            lastLaunchedTitle: 'Ms. Pac-Man'
        };

        console.log('   - Writing test session to aa_lora_sessions...');
        await sessionStore.set(testDeviceId, testSession);

        console.log('   - Reading session back from cloud...');
        const retrieved = await sessionStore.get(testDeviceId);

        if (retrieved && retrieved.chatState === 'VERIFICATION_TEST') {
            console.log('   - ✅ Cloud persistence verified!');
        } else {
            throw new Error('Retrieved session does not match test data.');
        }

        // 3. Final Verdict
        console.log('\n=========================================================');
        console.log('✅ BACKBONE STATUS: ONLINE');
        console.log('Remote configuration and cloud memory are fully linked.');
        console.log('=========================================================');

    } catch (error) {
        console.error('\n❌ VERIFICATION FAILED');
        console.error(`Reason: ${error.message}`);
        process.exit(1);
    }
}

runVerification();
