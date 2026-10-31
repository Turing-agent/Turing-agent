import React, { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Key, ShieldCheck, X, Check, Code2, ExternalLink, ArrowRight, Sparkles, AlertCircle } from 'lucide-react'

export function GitHubAuthModal({ isOpen, onClose, onAuthenticated, currentToken }) {
  const [tokenInput, setTokenInput] = useState(currentToken || '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  if (!isOpen) return null

  const handleVerify = async (pat) => {
    const testToken = (pat || tokenInput).trim()
    setLoading(true)
    setError(null)

    try {
      if (!testToken) {
        // Public/Demo mode without personal token
        localStorage.removeItem('turing_gh_pat')
        onAuthenticated({
          authenticated: false,
          user: { login: 'Community Explorer', avatar_url: null },
          token: null
        })
        onClose()
        return
      }

      const res = await fetch('https://api.github.com/user', {
        headers: {
          'Authorization': `Bearer ${testToken}`,
          'Accept': 'application/vnd.github+json'
        }
      })

      if (res.ok) {
        const user = await res.json()
        localStorage.setItem('turing_gh_pat', testToken)
        onAuthenticated({
          authenticated: true,
          user: {
            login: user.login,
            name: user.name || user.login,
            avatar_url: user.avatar_url,
            repos_url: user.repos_url
          },
          token: testToken
        })
        onClose()
      } else {
        setError('Invalid GitHub Personal Access Token. Please verify permissions.')
      }
    } catch (err) {
      setError(`Network error verifying token: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  const handleDemoConnect = () => {
    // Quick connect with demo mode (uses backend server token for public repos)
    localStorage.removeItem('turing_gh_pat')
    onAuthenticated({
      authenticated: false,
      isDemo: true,
      user: { login: 'Turing Explorer', avatar_url: null },
      token: null
    })
    onClose()
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <motion.div 
        className="modal-card" 
        onClick={(e) => e.stopPropagation()}
        initial={{ opacity: 0, scale: 0.95, y: 15 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 15 }}
      >
        <div className="modal-header">
          <div className="modal-title">
            <span className="brand-mark small"><Code2 size={15}/></span>
            <span>Connect GitHub Account</span>
          </div>
          <button className="close-button" onClick={onClose}><X size={16}/></button>
        </div>

        <div className="modal-body">
          <p className="modal-desc">
            Connect your GitHub account or Personal Access Token to inspect private repositories and analyze commit DAGs.
          </p>

          <div className="input-group">
            <label><Key size={13}/> GitHub Personal Access Token (Classic or Fine-Grained)</label>
            <div className="input-wrapper">
              <input 
                type="password"
                placeholder="ghp_xxxxxxxxxxxxxxxxxxxx"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleVerify()}
              />
              <button 
                className="button button-small" 
                onClick={() => handleVerify()}
                disabled={loading}
              >
                {loading ? <span className="spinner small"/> : <><Check size={14}/> Connect</>}
              </button>
            </div>
            <span className="input-hint">
              Requires <code>repo</code> scope to list private repositories. Stored strictly in your browser.
            </span>
          </div>

          {error && (
            <div className="error-banner">
              <AlertCircle size={15}/>
              <span>{error}</span>
            </div>
          )}

          <div className="divider"><span>OR</span></div>

          <div className="demo-box" onClick={handleDemoConnect}>
            <div className="demo-info">
              <div className="demo-title"><Sparkles size={14}/> Explore Public Repositories (No Account)</div>
              <p>Explore public open-source repositories (e.g. <code>YASHK-arch/eventyay_Sandbox</code>) using Turing's server gateway.</p>
            </div>
            <ArrowRight size={16} className="demo-arrow"/>
          </div>
        </div>

        <div className="modal-footer">
          <a 
            href="https://github.com/settings/tokens/new?scopes=repo&description=Turing-Agent-Dashboard" 
            target="_blank" 
            rel="noreferrer"
            className="text-link small"
          >
            Create token on GitHub <ExternalLink size={12}/>
          </a>
          <button className="button-ghost" onClick={onClose}>Cancel</button>
        </div>
      </motion.div>
    </div>
  )
}
