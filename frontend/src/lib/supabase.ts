import { createClient } from '@supabase/supabase-js'
import { publicConfig } from '../generated/public-config'

const url = publicConfig.useLocalProxy
  ? `${window.location.origin}/supabase`
  : publicConfig.url
const publishableKey = publicConfig.publishableKey

export const isSupabaseConfigured = Boolean(url && publishableKey)

export const supabase = createClient(
  url || 'http://127.0.0.1:54321',
  publishableKey || 'development-placeholder-publishable-key',
  {
    auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
  },
)
