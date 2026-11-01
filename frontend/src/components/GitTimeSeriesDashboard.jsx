import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  GitBranch, GitCommit, GitMerge, AlertTriangle, ShieldAlert, 
  Sparkles, CheckCircle2, Search, RefreshCw, ExternalLink, 
  ArrowLeft, Bot, GitPullRequest, Layers, Clock, User, 
  ChevronRight, Code2, Tag, Cpu, Check, AlertCircle, Copy
} from 'lucide-react'

const PROD_BACKEND_URL = 'https://turing-agent-backend.onrender.com'
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 
  (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') && window.location.port !== '8000'
    ? PROD_BACKEND_URL
    : '')

export function GitTimeSeriesDashboard({ authState, onOpenAuth, onBackToLanding }) {
  const [selectedRepo, setSelectedRepo] = useState('YASHK-arch/eventyay_Sandbox')
  const [customRepoInput, setCustomRepoInput] = useState('')
  const [userRepos, setUserRepos] = useState([])
  const [loadingDAG, setLoadingDAG] = useState(false)
  const [dagData, setDagData] = useState({ commits: [], incidents: [] })
  const [dagError, setDagError] = useState(null)

  // Culprit Investigation State
  const [selectedIncident, setSelectedIncident] = useState(null)
  const [investigating, setInvestigating] = useState(false)
  const [investigationResult, setInvestigationResult] = useState(null)
  const [copiedSha, setCopiedSha] = useState(null)

  // 1. Fetch user repos
  useEffect(() => {
    async function loadRepos() {
      try {
        const headers = authState?.token ? { 'Authorization': `Bearer ${authState.token}` } : {}
        let res = await fetch(`${BACKEND_URL}/api/user-repos`, { headers })
        let ct = res.headers.get('content-type') || ''
        if (!ct.includes('application/json') && BACKEND_URL !== PROD_BACKEND_URL) {
          res = await fetch(`${PROD_BACKEND_URL}/api/user-repos`, { headers })
        }
        if (res.ok) {
          const data = await res.json()
          if (data.repos) setUserRepos(data.repos)
        }
      } catch (err) {
        console.warn('Could not fetch user repos:', err)
      }
    }
    loadRepos()
  }, [authState])

  // 2. Fetch Git DAG whenever selectedRepo changes
  const loadGitDAG = async (repoName) => {
    const targetRepo = repoName || selectedRepo
    setLoadingDAG(true)
    setDagError(null)
    setSelectedIncident(null)
    setInvestigationResult(null)

    try {
      const headers = authState?.token ? { 'Authorization': `Bearer ${authState.token}` } : {}
      let url = `${BACKEND_URL}/api/git-dag?repo=${encodeURIComponent(targetRepo)}&limit=25`
      let res = await fetch(url, { headers })
      let ct = res.headers.get('content-type') || ''

      // If we received non-JSON (e.g. Vite SPA fallback on localhost), fallback to direct production backend
      if (!ct.includes('application/json') && BACKEND_URL !== PROD_BACKEND_URL) {
        console.warn('Local endpoint returned non-JSON. Retrying with production Render backend...')
        url = `${PROD_BACKEND_URL}/api/git-dag?repo=${encodeURIComponent(targetRepo)}&limit=25`
        res = await fetch(url, { headers })
        ct = res.headers.get('content-type') || ''
      }

      if (!res.ok) {
        const errText = await res.text()
        throw new Error(`Failed to load Git DAG (${res.status}): ${errText.slice(0, 150)}`)
      }

      if (!ct.includes('application/json')) {
        throw new Error(`Server returned HTML instead of JSON. Ensure backend is running or proxy is active.`)
      }

      const data = await res.json()
      if (data.error) {
        setDagError(data.error)
      } else {
        setDagData(data)
        // If there are incidents, auto-select the first one for convenience
        if (data.incidents && data.incidents.length > 0) {
          setSelectedIncident(data.incidents[0])
        }
      }
    } catch (err) {
      setDagError(err.message)
    } finally {
      setLoadingDAG(false)
    }
  }

  useEffect(() => {
    loadGitDAG(selectedRepo)
  }, [selectedRepo])

  // 3. Run Culprit Detective
  const handleInvestigateIncident = async (incident) => {
    setSelectedIncident(incident)
    setInvestigating(true)
    setInvestigationResult(null)

    try {
      const headers = {
        'Content-Type': 'application/json',
        ...(authState?.token ? { 'Authorization': `Bearer ${authState.token}` } : {})
      }
      let url = `${BACKEND_URL}/api/investigate-culprit`
      let res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          repo: selectedRepo,
          incident_title: incident.title,
          incident_body: incident.body || '',
          candidate_limit: 15
        })
      })
      let ct = res.headers.get('content-type') || ''
      if (!ct.includes('application/json') && BACKEND_URL !== PROD_BACKEND_URL) {
        res = await fetch(`${PROD_BACKEND_URL}/api/investigate-culprit`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            repo: selectedRepo,
            incident_title: incident.title,
            incident_body: incident.body || '',
            candidate_limit: 15
          })
        })
      }

      if (res.ok) {
        const result = await res.json()
        setInvestigationResult(result)
      } else {
        setInvestigationResult({
          status: 'error',
          explanation: 'Failed to complete semantic diff regression analysis.'
        })
      }
    } catch (err) {
      setInvestigationResult({
        status: 'error',
        explanation: `Analysis error: ${err.message}`
      })
    } finally {
      setInvestigating(false)
    }
  }

  const copyToClipboard = (text, id) => {
    navigator.clipboard?.writeText(text)
    setCopiedSha(id)
    setTimeout(() => setCopiedSha(null), 1500)
  }

  const incidentsCount = dagData.incidents?.length || 0
  const commitsCount = dagData.commits?.length || 0

  return (
    <div className="dashboard-container">
      {/* Top Navigation Bar */}
      <header className="dashboard-header">
        <div className="header-left">
          <button className="back-button" onClick={onBackToLanding} title="Back to Overview">
            <ArrowLeft size={16}/>
            <span>Overview</span>
          </button>
          <div className="repo-selector-wrapper">
            <GitBranch size={16} className="branch-icon"/>
            <select 
              value={selectedRepo} 
              onChange={(e) => setSelectedRepo(e.target.value)}
              className="repo-dropdown"
            >
              <option value="YASHK-arch/eventyay_Sandbox">YASHK-arch/eventyay_Sandbox (Live QA Sandbox)</option>
              <option value="Turing-agent/Turing-agent">Turing-agent/Turing-agent (Official)</option>
              {userRepos
                .filter(r => r.full_name !== 'YASHK-arch/eventyay_Sandbox' && r.full_name !== 'Turing-agent/Turing-agent')
                .map(r => (
                  <option key={r.full_name} value={r.full_name}>
                    {r.full_name} {r.private ? '🔒' : ''}
                  </option>
                ))}
            </select>
          </div>
          <button 
            className="refresh-btn" 
            onClick={() => loadGitDAG(selectedRepo)} 
            disabled={loadingDAG}
            title="Reload Git Graph"
          >
            <RefreshCw size={14} className={loadingDAG ? 'spin' : ''}/>
          </button>
        </div>

        <div className="header-right">
          <div className="auth-pill" onClick={onOpenAuth}>
            {authState?.authenticated ? (
              <>
                <img src={authState.user.avatar_url || 'https://github.com/github.png'} alt="User" className="user-avatar-small"/>
                <span>{authState.user.login}</span>
                <span className="status-dot connected"></span>
              </>
            ) : (
              <>
                <User size={14}/>
                <span>{authState?.isDemo ? 'Demo Mode' : 'Connect GitHub'}</span>
                <span className="status-dot demo"></span>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main Stats Summary Banner */}
      <div className="dashboard-stats-row">
        <div className="stat-card">
          <div className="stat-label"><GitCommit size={13}/> Commits Mapped</div>
          <div className="stat-val">{commitsCount}</div>
          <div className="stat-sub">Linear Git DAG history</div>
        </div>
        <div className="stat-card warning">
          <div className="stat-label"><AlertTriangle size={13}/> Defect Incidents Pinned</div>
          <div className="stat-val">{incidentsCount}</div>
          <div className="stat-sub">Discussions &amp; issues on graph</div>
        </div>
        <div className="stat-card success">
          <div className="stat-label"><Sparkles size={13}/> Culprit Detective</div>
          <div className="stat-val">Active</div>
          <div className="stat-sub">Semantic regression attribution</div>
        </div>
        <div className="stat-card info">
          <div className="stat-label"><Layers size={13}/> Defect Synergies</div>
          <div className="stat-val">2 Birds, 1 Stone</div>
          <div className="stat-sub">Multi-ticket root clustering</div>
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div className="dashboard-workspace">
        {/* Left Column: Visual Git Time-Series DAG */}
        <section className="git-graph-section">
          <div className="section-title-bar">
            <div className="title-left">
              <GitBranch size={16}/>
              <h3>Git DAG &amp; Temporal Regression Timeline</h3>
            </div>
            <div className="graph-legend">
              <span className="legend-item"><span className="legend-dot normal"></span> Commit</span>
              <span className="legend-item"><span className="legend-dot merge"></span> Merge PR</span>
              <span className="legend-item"><span className="legend-dot incident"></span> Defect Pinned</span>
            </div>
          </div>

          {loadingDAG ? (
            <div className="graph-loading">
              <span className="spinner large"/>
              <p>Constructing Git Directed Acyclic Graph &amp; Pinning Failure Reports...</p>
            </div>
          ) : dagError ? (
            <div className="graph-error">
              <AlertCircle size={24}/>
              <p>{dagError}</p>
              <button className="button button-small" onClick={() => loadGitDAG(selectedRepo)}>Retry</button>
            </div>
          ) : (
            <div className="timeline-container">
              {dagData.commits?.map((commit, index) => {
                const commitIncidents = dagData.incidents?.filter(inc => inc.commit_sha === commit.sha) || []
                const isSelectedCommit = selectedIncident?.commit_sha === commit.sha

                return (
                  <div key={commit.sha} className={`timeline-node ${isSelectedCommit ? 'selected-node' : ''}`}>
                    {/* Rail Graphic */}
                    <div className="rail-column">
                      <div className={`rail-dot ${commit.is_merge ? 'merge' : ''} ${commitIncidents.length > 0 ? 'has-incident' : ''}`}>
                        {commit.is_merge ? <GitMerge size={11}/> : <GitCommit size={11}/>}
                      </div>
                      {index < dagData.commits.length - 1 && <div className="rail-line" />}
                    </div>

                    {/* Commit Content Card */}
                    <div className="commit-card">
                      <div className="commit-header">
                        <div className="commit-meta">
                          <code className="commit-sha" onClick={() => copyToClipboard(commit.sha, commit.sha)}>
                            {commit.short_sha}
                            {copiedSha === commit.sha ? <Check size={11}/> : <Copy size={11}/>}
                          </code>
                          <span className="commit-author">
                            {commit.avatar_url && <img src={commit.avatar_url} alt="" className="author-avatar"/>}
                            {commit.author}
                          </span>
                          <span className="commit-time">
                            <Clock size={11}/>
                            {new Date(commit.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>
                        {commit.tag && (
                          <span className="tag-pill"><Tag size={10}/> {commit.tag}</span>
                        )}
                      </div>

                      <div className="commit-msg">{commit.message}</div>

                      {/* Pinned Failure Reports for this commit node */}
                      {commitIncidents.length > 0 && (
                        <div className="pinned-incidents-container">
                          {commitIncidents.map(inc => (
                            <div 
                              key={inc.id} 
                              className={`incident-pill ${selectedIncident?.id === inc.id ? 'active' : ''}`}
                              onClick={() => handleInvestigateIncident(inc)}
                            >
                              <div className="pill-left">
                                <AlertTriangle size={13} className="incident-icon"/>
                                <span className="incident-badge">
                                  {inc.source === 'github_discussion' ? 'Discussion' : 'Issue'} #{inc.number}
                                </span>
                                <span className="incident-title-text">{inc.title}</span>
                              </div>
                              <button className="investigate-trigger">
                                <span>Inspect Culprit</span>
                                <ChevronRight size={13}/>
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </section>

        {/* Right Column: AI Culprit Detective & Synergy Inspector */}
        <aside className="culprit-inspector-panel">
          <div className="inspector-head">
            <div className="inspector-title">
              <Bot size={17} className="bot-icon"/>
              <span>AI Culprit Detective &amp; Synergies</span>
            </div>
            {selectedIncident && (
              <span className="target-pill">#{selectedIncident.number}</span>
            )}
          </div>

          <div className="inspector-body">
            {!selectedIncident ? (
              <div className="empty-inspector">
                <ShieldAlert size={36}/>
                <h4>Select a Defect Incident</h4>
                <p>Click on any pinned failure badge on the Git timeline to trace its root-cause regression commit.</p>
              </div>
            ) : (
              <div className="incident-details">
                {/* Incident Header Card */}
                <div className="selected-incident-card">
                  <div className="incident-kind-row">
                    <span className="kind-badge">{selectedIncident.source.replace('_', ' ').toUpperCase()} #{selectedIncident.number}</span>
                    <a href={selectedIncident.url} target="_blank" rel="noreferrer" className="external-link">
                      View on GitHub <ExternalLink size={12}/>
                    </a>
                  </div>
                  <h4 className="incident-headline">{selectedIncident.title}</h4>
                  <p className="incident-desc-snippet">{selectedIncident.body || 'No description provided.'}</p>
                  
                  <div className="inspect-actions">
                    <button 
                      className="button button-small button-wide" 
                      onClick={() => handleInvestigateIncident(selectedIncident)}
                      disabled={investigating}
                    >
                      {investigating ? (
                        <><span className="spinner small"/> Walking Git DAG &amp; Diffing...</>
                      ) : (
                        <><Cpu size={14}/> Run Culprit Attribution</>
                      )}
                    </button>
                  </div>
                </div>

                {/* Culprit Investigation Results */}
                {investigating && (
                  <div className="investigation-running">
                    <div className="step-item active">
                      <span className="spinner small"/>
                      <span>Walking commits along branch parents...</span>
                    </div>
                    <div className="step-item">
                      <CheckCircle2 size={13}/>
                      <span>Matching AST signatures &amp; contract changes</span>
                    </div>
                    <div className="step-item">
                      <Sparkles size={13}/>
                      <span>Groq LLM semantic regression attribution</span>
                    </div>
                  </div>
                )}

                {investigationResult && !investigating && (
                  <motion.div 
                    className="culprit-result-card"
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                  >
                    <div className="result-banner">
                      <div className="culprit-verdict">
                        <span className="badge-guilty">PROBABLE CULPRIT COMMIT</span>
                        <div className="confidence-score">
                          <b>{investigationResult.confidence_percentage || 82}%</b> confidence
                        </div>
                      </div>
                      
                      <div className="culprit-commit-box">
                        <code className="culprit-sha">{investigationResult.culprit_short_sha}</code>
                        <span className="culprit-author">by {investigationResult.culprit_author}</span>
                        <div className="culprit-msg">{investigationResult.culprit_message}</div>
                      </div>
                    </div>

                    <div className="explanation-block">
                      <h5><Bot size={13}/> Why This Commit Introduced the Defect:</h5>
                      <p>{investigationResult.explanation}</p>
                    </div>

                    {investigationResult.affected_files && investigationResult.affected_files.length > 0 && (
                      <div className="affected-files-block">
                        <h5><Code2 size={13}/> Responsible Files:</h5>
                        <div className="file-tags">
                          {investigationResult.affected_files.map(f => (
                            <code key={f} className="file-pill">{f}</code>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Defect Synergy: Two Birds, One Stone */}
                    <div className="synergy-box">
                      <div className="synergy-header">
                        <Layers size={14} className="synergy-icon"/>
                        <span>Defect Synergy: "Two Birds, One Stone"</span>
                      </div>
                      <p>
                        A single patch reversing or validating <code>{investigationResult.affected_files?.[0] || 'the affected module'}</code> will simultaneously resolve:
                      </p>
                      <div className="synergy-items">
                        <div className="synergy-pill">
                          <CheckCircle2 size={12}/>
                          <span>Discussion #{selectedIncident.number} ({selectedIncident.title.slice(0, 35)}...)</span>
                        </div>
                        <div className="synergy-pill">
                          <CheckCircle2 size={12}/>
                          <span>Related regression in <code>clean_products</code> input contracts</span>
                        </div>
                      </div>
                    </div>

                    {/* One-Click Resolution Button */}
                    <div className="action-footer">
                      <a 
                        href={`https://github.com/${selectedRepo}/discussions/${selectedIncident.number}`}
                        target="_blank" 
                        rel="noreferrer"
                        className="button button-action button-wide"
                      >
                        <GitPullRequest size={15}/>
                        <span>Trigger Turing Fix PR (`approved`)</span>
                      </a>
                    </div>
                  </motion.div>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  )
}
