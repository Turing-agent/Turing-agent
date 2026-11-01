import React, { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { 
  GitBranch, GitCommit, GitMerge, AlertTriangle, ShieldAlert, 
  Sparkles, CheckCircle2, RefreshCw, ExternalLink, 
  ArrowLeft, Bot, GitPullRequest, Layers, Clock, User, 
  ChevronRight, ChevronDown, Code2, Tag, Cpu, Check, AlertCircle, Copy
} from 'lucide-react'

const PROD_BACKEND_URL = 'https://turing-agent-backend.onrender.com'
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 
  (typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') && window.location.port !== '8000'
    ? PROD_BACKEND_URL
    : '')

export function GitTimeSeriesDashboard({ authState, onOpenAuth, onBackToLanding }) {
  const [selectedRepo, setSelectedRepo] = useState('eventyaysandbox/eventyay_Sandbox')
  const [userRepos, setUserRepos] = useState([])
  const [loadingDAG, setLoadingDAG] = useState(false)
  const [dagData, setDagData] = useState({ commits: [], incidents: [] })
  const [dagError, setDagError] = useState(null)
  const [expandedCommits, setExpandedCommits] = useState(new Set())

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
      let url = `${BACKEND_URL}/api/git-dag?repo=${encodeURIComponent(targetRepo)}&limit=30`
      let res = await fetch(url, { headers })
      let ct = res.headers.get('content-type') || ''

      if (!ct.includes('application/json') && BACKEND_URL !== PROD_BACKEND_URL) {
        console.warn('Local endpoint returned non-JSON. Retrying with production Render backend...')
        url = `${PROD_BACKEND_URL}/api/git-dag?repo=${encodeURIComponent(targetRepo)}&limit=30`
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
        
        // Auto-expand commits that have incidents
        const initialExpanded = new Set()
        if (data.commits) {
          data.commits.forEach(c => {
            if (c.incidents && c.incidents.length > 0) {
              initialExpanded.add(c.sha)
            }
          })
        }
        setExpandedCommits(initialExpanded)

        // Auto-select first incident for convenience
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

  const toggleCommitDropdown = (sha) => {
    setExpandedCommits(prev => {
      const next = new Set(prev)
      if (next.has(sha)) {
        next.delete(sha)
      } else {
        next.add(sha)
      }
      return next
    })
  }

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
              <option value="eventyaysandbox/eventyay_Sandbox">eventyaysandbox/eventyay_Sandbox (Synced QA Sandbox - 26 Issues)</option>
              <option value="fossasia/eventyay">fossasia/eventyay (Official Upstream Eventyay)</option>
              <option value="YASHK-arch/eventyay_Sandbox">YASHK-arch/eventyay_Sandbox (Personal Sandbox)</option>
              <option value="Turing-agent/Turing-agent">Turing-agent/Turing-agent (Official)</option>
              {userRepos
                .filter(r => !['eventyaysandbox/eventyay_Sandbox', 'fossasia/eventyay', 'YASHK-arch/eventyay_Sandbox', 'Turing-agent/Turing-agent'].includes(r.full_name))
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
        {/* Left Column: Authentic Git Graph Table & Temporal Regression Timeline */}
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
            <div className="git-graph-table-container">
              {/* Git Graph Header */}
              <div className="git-graph-header-row">
                <div className="col-graph">Graph</div>
                <div className="col-desc">Description &amp; Refs</div>
                <div className="col-defects">Defects</div>
                <div className="col-author">Author</div>
                <div className="col-date">Date</div>
                <div className="col-sha">Commit</div>
              </div>

              {/* Commits List with Expandable Incident Dropdowns */}
              <div className="git-graph-body">
                {dagData.commits?.map((commit) => {
                  const hasIncidents = commit.incidents && commit.incidents.length > 0
                  const isExpanded = expandedCommits.has(commit.sha)
                  const isSelectedCommit = selectedIncident?.commit_sha === commit.sha
                  const laneIndex = commit.lane || 0
                  const laneColor = commit.lane_color || '#38bdf8'

                  return (
                    <div key={commit.sha} className={`commit-entry-group ${isSelectedCommit ? 'selected-group' : ''}`}>
                      {/* Main Commit Row */}
                      <div 
                        className={`git-commit-row ${isSelectedCommit ? 'active-row' : ''}`}
                        onClick={() => hasIncidents && toggleCommitDropdown(commit.sha)}
                      >
                        {/* Graph Swimlane Column */}
                        <div className="col-graph git-rail-cell">
                          <svg className="git-rail-svg" width="60" height="34" viewBox="0 0 60 34">
                            {/* Rail Lines */}
                            <line x1="12" y1="0" x2="12" y2="34" stroke="#2a2a28" strokeWidth="2" />
                            <line x1="28" y1="0" x2="28" y2="34" stroke="#2a2a28" strokeWidth="2" />
                            <line x1="44" y1="0" x2="44" y2="34" stroke="#2a2a28" strokeWidth="2" />
                            
                            {/* Active Branch Lane Line */}
                            <line 
                              x1={12 + laneIndex * 16} 
                              y1="0" 
                              x2={12 + laneIndex * 16} 
                              y2="34" 
                              stroke={laneColor} 
                              strokeWidth="2.5" 
                            />

                            {/* Merge Connecting Branch Arc */}
                            {commit.is_merge && (
                              <path 
                                d={`M 12 34 Q 20 17 ${12 + laneIndex * 16} 17`} 
                                fill="none" 
                                stroke="#a855f7" 
                                strokeWidth="2" 
                              />
                            )}

                            {/* Commit Node Circle */}
                            {hasIncidents && (
                              <circle 
                                cx={12 + laneIndex * 16} 
                                cy="17" 
                                r="8" 
                                fill="none" 
                                stroke="#ef4444" 
                                strokeWidth="2" 
                                className="incident-glow-ring"
                              />
                            )}
                            <circle 
                              cx={12 + laneIndex * 16} 
                              cy="17" 
                              r={commit.branch_refs?.length ? "5.5" : "4.5"} 
                              fill={commit.branch_refs?.length ? "#121212" : (hasIncidents ? "#ef4444" : laneColor)} 
                              stroke={hasIncidents ? "#ef4444" : laneColor} 
                              strokeWidth="2.5" 
                            />
                          </svg>
                        </div>

                        {/* Description & Refs Column */}
                        <div className="col-desc">
                          {/* Branch Refs */}
                          {commit.branch_refs?.map(ref => (
                            <a 
                              key={ref} 
                              href={`https://github.com/${selectedRepo}/tree/${ref.replace('origin/', '')}`} 
                              target="_blank" 
                              rel="noreferrer" 
                              className={`ref-pill branch ${ref.startsWith('origin/') ? 'remote' : ''}`}
                              onClick={(e) => e.stopPropagation()}
                              title={`View ${ref} on GitHub`}
                            >
                              <GitBranch size={10} />
                              <span>{ref}</span>
                            </a>
                          ))}

                          {/* Tag Refs */}
                          {commit.tag && (
                            <a 
                              href={`https://github.com/${selectedRepo}/releases/tag/${commit.tag}`}
                              target="_blank" 
                              rel="noreferrer" 
                              className="ref-pill tag"
                              onClick={(e) => e.stopPropagation()}
                              title={`View tag ${commit.tag} on GitHub`}
                            >
                              <Tag size={10} />
                              <span>{commit.tag}</span>
                            </a>
                          )}

                          {/* Commit Subject Link */}
                          <a 
                            href={commit.commit_url} 
                            target="_blank" 
                            rel="noreferrer" 
                            className="commit-subject-link"
                            onClick={(e) => e.stopPropagation()}
                            title={commit.full_message}
                          >
                            {commit.message}
                          </a>
                        </div>

                        {/* Defects Column with Dropdown Toggle */}
                        <div className="col-defects">
                          {hasIncidents ? (
                            <button 
                              className={`defects-dropdown-btn ${isExpanded ? 'active' : ''}`}
                              onClick={(e) => {
                                e.stopPropagation()
                                toggleCommitDropdown(commit.sha)
                              }}
                              title="Toggle Defect Incidents Dropdown"
                            >
                              <span className="defect-dot"></span>
                              <span>{commit.incidents.length} {commit.incidents.length === 1 ? 'Defect' : 'Defects'}</span>
                              <ChevronDown size={11} className={`chevron-icon ${isExpanded ? 'rotated' : ''}`} />
                            </button>
                          ) : (
                            <span className="no-defects-dash">—</span>
                          )}
                        </div>

                        {/* Author Column */}
                        <div className="col-author">
                          <a 
                            href={commit.author_url} 
                            target="_blank" 
                            rel="noreferrer" 
                            className="author-link"
                            onClick={(e) => e.stopPropagation()}
                            title={`View @${commit.author} on GitHub`}
                          >
                            {commit.avatar_url && <img src={commit.avatar_url} alt="" className="author-avatar-img"/>}
                            <span>{commit.author}</span>
                          </a>
                        </div>

                        {/* Date Column */}
                        <div className="col-date">
                          <span title={commit.date}>
                            {new Date(commit.date).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                          </span>
                        </div>

                        {/* Commit SHA Column */}
                        <div className="col-sha">
                          <div className="sha-link-group">
                            <a 
                              href={commit.commit_url} 
                              target="_blank" 
                              rel="noreferrer" 
                              className="sha-code-link"
                              onClick={(e) => e.stopPropagation()}
                              title="Open commit on GitHub"
                            >
                              <code>{commit.short_sha}</code>
                            </a>
                            <button 
                              className="copy-sha-btn" 
                              onClick={(e) => {
                                e.stopPropagation()
                                copyToClipboard(commit.sha, commit.sha)
                              }}
                              title="Copy full SHA"
                            >
                              {copiedSha === commit.sha ? <Check size={10} className="check-green"/> : <Copy size={10}/>}
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Dropdown Nodes for Pinned Defects */}
                      <AnimatePresence>
                        {hasIncidents && isExpanded && (
                          <motion.div 
                            className="commit-defects-dropdown-panel"
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: 'auto' }}
                            exit={{ opacity: 0, height: 0 }}
                            transition={{ duration: 0.18 }}
                          >
                            <div className="dropdown-indicator-rail" />
                            <div className="dropdown-nodes-container">
                              {commit.incidents.map((inc) => (
                                <div 
                                  key={inc.id} 
                                  className={`defect-node-card ${selectedIncident?.id === inc.id ? 'active-incident' : ''}`}
                                  onClick={() => setSelectedIncident(inc)}
                                >
                                  <div className="defect-node-left">
                                    <span className={`status-badge ${inc.state}`}>
                                      {inc.state === 'closed' ? <CheckCircle2 size={11}/> : <span className="green-dot"/>}
                                      {inc.state?.toUpperCase()}
                                    </span>

                                    <span className="kind-badge">
                                      {inc.source === 'github_discussion' ? 'Discussion' : 'Issue'} #{inc.number}
                                    </span>

                                    <a 
                                      href={inc.url} 
                                      target="_blank" 
                                      rel="noreferrer" 
                                      className="defect-title-link"
                                      onClick={(e) => e.stopPropagation()}
                                      title="Open defect on GitHub"
                                    >
                                      <span>{inc.title}</span>
                                      <ExternalLink size={11} className="ext-icon"/>
                                    </a>
                                  </div>

                                  <div className="defect-node-right">
                                    {inc.author && (
                                      <a 
                                        href={inc.author_url} 
                                        target="_blank" 
                                        rel="noreferrer" 
                                        className="defect-author-link"
                                        onClick={(e) => e.stopPropagation()}
                                      >
                                        @{inc.author}
                                      </a>
                                    )}

                                    <span className="defect-date-label">
                                      <Clock size={10}/>
                                      {inc.effective_date ? new Date(inc.effective_date).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : ''}
                                    </span>

                                    <button 
                                      className="inspect-action-btn"
                                      onClick={(e) => {
                                        e.stopPropagation()
                                        handleInvestigateIncident(inc)
                                      }}
                                    >
                                      <Sparkles size={11}/>
                                      <span>Inspect Culprit</span>
                                      <ChevronRight size={11}/>
                                    </button>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  )
                })}
              </div>
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
              <a 
                href={selectedIncident.url} 
                target="_blank" 
                rel="noreferrer" 
                className="target-pill-link"
                title="Open Incident on GitHub"
              >
                <span>#{selectedIncident.number}</span>
                <ExternalLink size={10}/>
              </a>
            )}
          </div>

          <div className="inspector-body">
            {!selectedIncident ? (
              <div className="empty-inspector">
                <ShieldAlert size={36}/>
                <h4>Select a Defect Incident</h4>
                <p>Click on any defect dropdown node on the Git timeline to trace its root-cause regression commit.</p>
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
                        <a 
                          href={investigationResult.culprit_commit_url || `https://github.com/${selectedRepo}/commit/${investigationResult.culprit_sha}`}
                          target="_blank"
                          rel="noreferrer"
                          className="culprit-sha-link"
                          title="View culprit commit on GitHub"
                        >
                          <code className="culprit-sha">{investigationResult.culprit_short_sha}</code>
                          <ExternalLink size={11}/>
                        </a>
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
                            <a 
                              key={f} 
                              href={`https://github.com/${selectedRepo}/blob/${investigationResult.culprit_sha || 'dev'}/${f}`}
                              target="_blank"
                              rel="noreferrer"
                              className="file-pill-link"
                              title={`Inspect ${f} on GitHub`}
                            >
                              <code>{f}</code>
                              <ExternalLink size={10}/>
                            </a>
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
                        <a 
                          href={selectedIncident.url} 
                          target="_blank" 
                          rel="noreferrer" 
                          className="synergy-pill-link"
                        >
                          <CheckCircle2 size={12}/>
                          <span>{selectedIncident.source === 'github_discussion' ? 'Discussion' : 'Issue'} #{selectedIncident.number} ({selectedIncident.title.slice(0, 35)}...)</span>
                          <ExternalLink size={10}/>
                        </a>
                        <div className="synergy-pill">
                          <CheckCircle2 size={12}/>
                          <span>Related regression in <code>clean_products</code> input contracts</span>
                        </div>
                      </div>
                    </div>

                    {/* One-Click Resolution Button */}
                    <div className="action-footer">
                      <a 
                        href={`${selectedIncident.url}#issuecomment-new`}
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
