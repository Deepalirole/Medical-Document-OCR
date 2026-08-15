import type { Session } from '@supabase/supabase-js'
import {
  CheckCircle2,
  Eye,
  EyeOff,
  FileScan,
  LockKeyhole,
  Mail,
  ShieldCheck,
  User,
  UserPlus,
} from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { isSupabaseConfigured, supabase } from '../lib/supabase'

export function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [mode, setMode] = useState<'signin' | 'signup'>('signin')

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)

  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [successMessage, setSuccessMessage] = useState('')

  useEffect(() => {
    void supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession)
      setLoading(false)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  async function handleSignIn(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSuccessMessage('')
    setSubmitting(true)
    try {
      const { error: authError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      })
      if (authError) setError(authError.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleSignUp(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSuccessMessage('')

    if (password !== confirmPassword) {
      setError('Passwords do not match. Please re-enter your password.')
      return
    }
    if (password.length < 6) {
      setError('Password must be at least 6 characters long.')
      return
    }

    setSubmitting(true)
    try {
      const displayName = fullName.trim() || email.split('@')[0]
      const { data, error: authError } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: {
          data: {
            display_name: displayName,
          },
        },
      })

      if (authError) {
        setError(authError.message)
      } else if (data.session) {
        setSession(data.session)
      } else {
        setSuccessMessage(
          'Account created successfully! Please sign in with your email and password.',
        )
        setMode('signin')
        setPassword('')
        setConfirmPassword('')
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) {
    return (
      <div className="grid min-h-screen place-items-center bg-linen text-evergreen">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-3 border-evergreen border-t-transparent" />
          <p className="text-sm font-semibold">Checking secure session…</p>
        </div>
      </div>
    )
  }

  if (session) return children

  return (
    <main className="grid min-h-screen bg-linen lg:grid-cols-[1.1fr_0.9fr]">
      {/* Left Brand Panel */}
      <section className="hidden flex-col justify-between bg-evergreen p-14 text-white lg:flex">
        <div className="flex items-center gap-3 text-sm font-semibold uppercase tracking-[0.22em] text-emerald-100">
          <FileScan size={22} /> Evidence Studio
        </div>
        <div className="max-w-xl">
          <p className="mb-6 font-mono text-sm text-emerald-200">
            SOURCE → EVIDENCE → REVIEW → APPROVAL
          </p>
          <h1 className="text-6xl font-semibold leading-[1.04] tracking-tight">
            Every transcription stays tied to the page.
          </h1>
          <p className="mt-7 max-w-lg text-lg leading-8 text-emerald-100/80">
            A human-in-the-loop workspace for digitizing prescriptions with full OCR lineage and
            immutable version control.
          </p>
        </div>
        <div className="flex items-center gap-6 text-xs text-emerald-100/70">
          <span className="flex items-center gap-1.5">
            <ShieldCheck size={16} className="text-emerald-300" /> Private files
          </span>
          <span>·</span>
          <span>Organization isolation</span>
          <span>·</span>
          <span>Versioned approval</span>
        </div>
      </section>

      {/* Right Auth Panel */}
      <section className="grid place-items-center p-6 sm:p-10">
        <div className="w-full max-w-md rounded-3xl bg-white p-8 shadow-panel sm:p-10">
          {/* Header Icon */}
          <div className="mb-6 inline-flex rounded-2xl bg-mint p-3 text-evergreen">
            {mode === 'signin' ? <LockKeyhole size={24} /> : <UserPlus size={24} />}
          </div>

          {/* Mode Switcher Tabs */}
          <div className="mb-6 grid grid-cols-2 rounded-xl bg-slate-100 p-1 text-xs font-bold">
            <button
              type="button"
              onClick={() => {
                setMode('signin')
                setError('')
                setSuccessMessage('')
              }}
              className={`rounded-lg py-2 transition ${
                mode === 'signin'
                  ? 'bg-white text-evergreen shadow-xs'
                  : 'text-slate-500 hover:text-ink'
              }`}
            >
              Sign In
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('signup')
                setError('')
                setSuccessMessage('')
              }}
              className={`rounded-lg py-2 transition ${
                mode === 'signup'
                  ? 'bg-white text-evergreen shadow-xs'
                  : 'text-slate-500 hover:text-ink'
              }`}
            >
              Create Account
            </button>
          </div>

          <h2 className="text-2xl font-bold tracking-tight text-ink sm:text-3xl">
            {mode === 'signin' ? 'Welcome back' : 'Register new user'}
          </h2>
          <p className="mt-2 text-xs leading-5 text-slate-500 sm:text-sm">
            {mode === 'signin'
              ? 'Sign in to access your organization review queue and evidence studio.'
              : 'Create an account to start processing and reviewing prescription documents.'}
          </p>

          {!isSupabaseConfigured && (
            <div
              role="alert"
              className="mt-5 rounded-xl border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900"
            >
              Supabase environment variables are not configured yet.
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="mt-5 rounded-xl border border-red-200 bg-red-50 p-3 text-xs font-semibold text-red-700"
            >
              {error}
            </div>
          )}

          {successMessage && (
            <div
              role="status"
              className="mt-5 flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800"
            >
              <CheckCircle2 size={16} className="shrink-0 text-emerald-600 mt-0.5" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Form */}
          <form
            onSubmit={mode === 'signin' ? handleSignIn : handleSignUp}
            className="mt-6 space-y-4"
          >
            {/* Full Name (Only in Sign Up) */}
            {mode === 'signup' && (
              <div>
                <label
                  htmlFor="signup-name"
                  className="block text-xs font-semibold text-slate-700"
                >
                  Full Name / Display Name
                </label>
                <div className="relative mt-1.5">
                  <User size={16} className="absolute left-3.5 top-3 text-slate-400" />
                  <input
                    id="signup-name"
                    className="w-full rounded-xl border border-slate-200 py-2.5 pl-10 pr-4 text-xs text-ink outline-none transition focus:border-evergreen focus:ring-2 focus:ring-emerald-100"
                    type="text"
                    autoComplete="name"
                    placeholder="Dr. Sarah Sharma"
                    required
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                  />
                </div>
              </div>
            )}

            {/* Email */}
            <div>
              <label htmlFor="auth-email" className="block text-xs font-semibold text-slate-700">
                Email Address
              </label>
              <div className="relative mt-1.5">
                <Mail size={16} className="absolute left-3.5 top-3 text-slate-400" />
                <input
                  id="auth-email"
                  className="w-full rounded-xl border border-slate-200 py-2.5 pl-10 pr-4 text-xs text-ink outline-none transition focus:border-evergreen focus:ring-2 focus:ring-emerald-100"
                  type="email"
                  autoComplete="email"
                  placeholder="name@clinic.org"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label
                htmlFor="auth-password"
                className="block text-xs font-semibold text-slate-700"
              >
                Password
              </label>
              <div className="relative mt-1.5">
                <input
                  id="auth-password"
                  className="w-full rounded-xl border border-slate-200 py-2.5 pl-4 pr-10 text-xs text-ink outline-none transition focus:border-evergreen focus:ring-2 focus:ring-emerald-100"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  placeholder={mode === 'signup' ? 'At least 6 characters' : '••••••••'}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-2.5 text-slate-400 hover:text-slate-600"
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Confirm Password (Only in Sign Up) */}
            {mode === 'signup' && (
              <div>
                <label
                  htmlFor="signup-confirm-password"
                  className="block text-xs font-semibold text-slate-700"
                >
                  Confirm Password
                </label>
                <div className="relative mt-1.5">
                  <input
                    id="signup-confirm-password"
                    className="w-full rounded-xl border border-slate-200 py-2.5 pl-4 pr-10 text-xs text-ink outline-none transition focus:border-evergreen focus:ring-2 focus:ring-emerald-100"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="new-password"
                    placeholder="Re-enter password"
                    required
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                  />
                </div>
              </div>
            )}

            {/* Submit Button */}
            <button
              className="mt-6 w-full rounded-xl bg-evergreen py-3 text-xs font-bold text-white shadow-sm transition hover:bg-ink active:scale-98 disabled:cursor-not-allowed disabled:opacity-50"
              disabled={!isSupabaseConfigured || submitting}
              type="submit"
            >
              {submitting
                ? mode === 'signin'
                  ? 'Signing in…'
                  : 'Creating account…'
                : mode === 'signin'
                  ? 'Sign In Securely'
                  : 'Create Account & Start'}
            </button>
          </form>

          {/* Footer toggle prompt */}
          <div className="mt-6 border-t border-slate-100 pt-4 text-center text-xs text-slate-500">
            {mode === 'signin' ? (
              <p>
                Don't have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    setMode('signup')
                    setError('')
                    setSuccessMessage('')
                  }}
                  className="font-bold text-evergreen hover:underline cursor-pointer"
                >
                  Create one now
                </button>
              </p>
            ) : (
              <p>
                Already have an account?{' '}
                <button
                  type="button"
                  onClick={() => {
                    setMode('signin')
                    setError('')
                    setSuccessMessage('')
                  }}
                  className="font-bold text-evergreen hover:underline cursor-pointer"
                >
                  Sign in here
                </button>
              </p>
            )}
          </div>
        </div>
      </section>
    </main>
  )
}
