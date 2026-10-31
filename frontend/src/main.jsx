import React, { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { AnimatePresence, motion } from 'framer-motion'
import { 
  ArrowRight, Bot, Check, ChevronDown, Clipboard, Code2, 
  GitPullRequest, Menu, Play, ShieldCheck, Sparkles, Terminal, 
  Workflow, X, Activity, GitBranch 
} from 'lucide-react'
import './styles.css'
import { GitTimeSeriesDashboard } from './components/GitTimeSeriesDashboard'
import { GitHubAuthModal } from './components/GitHubAuthModal'

const installCommand = 'npx github:Turing-agent/Turing-agent'
const endpoints = [
  ['POST', '/run-tinyfish', 'Run a reproduction investigation and return a Markdown report.'],
  ['POST', '/triage-discussion', 'Draft a validation response and correlate related issues.'],
  ['POST', '/resolve-issue', 'Return proposed file changes and a commit-ready summary.'],
  ['POST', '/chat-turing', 'Send a conversational instruction to the Turing workflow.'],
  ['GET', '/api/git-dag', 'Fetch Git commit DAG with temporal defect incident pins.'],
  ['POST', '/api/investigate-culprit', 'Attribute root-cause regression commit for any defect.'],
]
const capabilities = [
  { icon: Bot, title: 'Live bug investigation', body: 'Turn issue context and optional screen recordings into a focused reproduction plan.', color: 'violet' },
  { icon: Sparkles, title: 'Maintainer-grade triage', body: 'Classify reports, ask sharper questions, and identify duplicate discussions.', color: 'cyan' },
  { icon: GitPullRequest, title: 'Patch proposals', body: 'Explore relevant source files and return structured, reviewable change suggestions.', color: 'lime' },
  { icon: GitBranch, title: 'Git time-series regression', body: 'Track failures along the commit DAG and pinpoint the guilty commit with 2-birds-1-stone synergies.', color: 'orange' },
]
const commands = [
  ['Install', 'npx github:Turing-agent/Turing-agent'],
  ['Run locally', 'uvicorn main:app --reload --port 8000'],
  ['Health check', 'curl http://127.0.0.1:8000/'],
]

function CopyButton({ value }) {
  const [copied, setCopied] = useState(false)
  const copy = async () => { await navigator.clipboard?.writeText(value); setCopied(true); setTimeout(() => setCopied(false), 1600) }
  return <button className="copy" onClick={copy} aria-label="Copy command">{copied ? <Check size={15} /> : <Clipboard size={15} />}</button>
}
function CodeBlock({ children, label = 'terminal' }) {
  return <div className="code-block"><div className="code-top"><span><i></i><i></i><i></i></span><span>{label}</span><CopyButton value={children} /></div><pre><code>{children}</code></pre></div>
}

function App() {
  const [currentView, setCurrentView] = useState(() => window.location.hash === '#dashboard' ? 'dashboard' : 'landing')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [activeCommand, setActiveCommand] = useState(0)
  const [authModalOpen, setAuthModalOpen] = useState(false)
  const [authState, setAuthState] = useState(() => {
    const pat = localStorage.getItem('turing_gh_pat')
    return {
      authenticated: !!pat,
      token: pat || null,
      user: pat ? { login: 'Connected Account', avatar_url: null } : null,
      isDemo: !pat
    }
  })

  // Synchronize hash with view
  useEffect(() => {
    const onHashChange = () => {
      if (window.location.hash === '#dashboard') {
        setCurrentView('dashboard')
      } else {
        setCurrentView('landing')
      }
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const handleOpenDashboard = () => {
    setMobileOpen(false)
    window.location.hash = '#dashboard'
    setCurrentView('dashboard')
    if (!authState.authenticated && !authState.isDemo) {
      setAuthModalOpen(true)
    }
  }

  const handleBackToLanding = () => {
    window.location.hash = ''
    setCurrentView('landing')
  }

  return (
    <>
      {currentView === 'dashboard' ? (
        <GitTimeSeriesDashboard 
          authState={authState}
          onOpenAuth={() => setAuthModalOpen(true)}
          onBackToLanding={handleBackToLanding}
        />
      ) : (
        <main>
          <div className="noise" />
          <header>
            <a className="brand" href="#top"><span className="brand-mark"><Bot size={19}/></span><span>TURING<span className="brand-dot">.</span></span></a>
            <nav className={mobileOpen ? 'open' : ''}>
              <a 
                href="#dashboard" 
                onClick={(e) => { e.preventDefault(); handleOpenDashboard(); }} 
                className="nav-dashboard-link"
              >
                <Activity size={13}/> Time-Series Dashboard <span className="nav-live-badge">LIVE</span>
              </a>
              <a href="#features">Capabilities</a>
              <a href="#setup">Get started</a>
              <a href="#usage">Usage</a>
              <a href="#api">API</a>
            </nav>
            <div className="header-actions">
              <a className="git-link" href="https://github.com/Turing-agent/Turing-agent" target="_blank" rel="noreferrer">
                <Code2 size={17}/> GitHub
              </a>
              <button className="button button-small" onClick={handleOpenDashboard}>
                <GitBranch size={14}/> Dashboard <ArrowRight size={14}/>
              </button>
              <button className="menu" onClick={() => setMobileOpen(!mobileOpen)}>
                {mobileOpen ? <X/> : <Menu/>}
              </button>
            </div>
          </header>

          <section id="top" className="hero section-grid">
            <motion.div className="hero-copy" initial={{opacity:0,y:24}} animate={{opacity:1,y:0}} transition={{duration:.65}}>
              <div className="eyebrow"><span></span> Autonomous GitHub QA &amp; Defect Graph</div>
              <h1>Your repository,<br/><em>always</em> watched.</h1>
              <p className="lede">Turing Agent turns GitHub discussions and reports into thoughtful triage, temporal regression DAGs, and commit-accurate fix proposals—powered by TinyFish.</p>
              <div className="hero-actions">
                <button className="button" onClick={handleOpenDashboard}>
                  Open Git Dashboard <ArrowRight size={17}/>
                </button>
                <a className="text-link" href="#usage">
                  <Play size={14} fill="currentColor"/> See how it works
                </a>
              </div>
              <div className="command-pill"><Terminal size={15}/><code>{installCommand}</code><CopyButton value={installCommand}/></div>
            </motion.div>
            <motion.div className="agent-panel" initial={{opacity:0,scale:.95}} animate={{opacity:1,scale:1}} transition={{duration:.7,delay:.15}}>
              <div className="panel-head"><div className="panel-title"><span className="pulse"></span> investigation / #248</div><span className="live">LIVE</span></div>
              <div className="panel-body">
                <div className="agent-message"><span className="agent-avatar"><Bot size={15}/></span><div><small>Turing Agent <b>• analyzing</b></small><p>I’ve mapped the report to the checkout flow and found a likely failure path.</p></div></div>
                <div className="signal-row"><span>REPRODUCTION PLAN</span><b>88% confidence</b></div>
                <div className="steps"><div><Check size={14}/><span>Read issue context &amp; media</span><time>done</time></div><div><Check size={14}/><span>Inspect target application</span><time>done</time></div><div className="current"><span className="spinner"></span><span>Generate root-cause report</span><time>now</time></div></div>
                <div className="finding"><Sparkles size={16}/><span><b>Potential cause:</b> stale state after coupon validation</span></div>
              </div>
              <div className="panel-footer"><span><span className="green-dot"></span> TinyFish connected</span><button onClick={handleOpenDashboard}>View in DAG <ArrowRight size={14}/></button></div>
            </motion.div>
            <div className="hero-orb orb-one"></div><div className="hero-orb orb-two"></div>
          </section>

          <section className="trust"><p>BUILT FOR THE MAINTAINER MOMENTS THAT MATTER</p><div><span>GitHub</span><span>FastAPI</span><span>n8n</span><span>TinyFish</span><span>Groq</span><span>Docker</span></div></section>

          <section id="features" className="features wrap">
            <div className="section-heading"><div className="eyebrow"><span></span> What Turing does</div><h2>A second set of eyes<br/>for every report.</h2><p>Give your community a faster path from “something broke” to an actionable engineering answer.</p></div>
            <div className="feature-grid">{capabilities.map((item, i) => <motion.article className="feature-card" key={item.title} initial={{opacity:0,y:18}} whileInView={{opacity:1,y:0}} viewport={{once:true}} transition={{delay:i*.08}}><div className={`icon ${item.color}`}><item.icon size={21}/></div><h3>{item.title}</h3><p>{item.body}</p><a href="#dashboard" onClick={(e) => { e.preventDefault(); handleOpenDashboard(); }}>Explore in DAG <ArrowRight size={14}/></a></motion.article>)}</div>
          </section>

          <section id="setup" className="setup section-grid"><div className="setup-copy"><div className="eyebrow"><span></span> Getting started</div><h2>From clone to<br/><em>first insight.</em></h2><p>Set up the backend locally, connect the automation workflow, and let Turing meet your contributors where they already are.</p><div className="check-list"><div><Check/> Python 3.10+ and Git</div><div><Check/> GitHub CLI authenticated</div><div><Check/> TinyFish and Groq API keys</div></div></div><div className="setup-card"><div className="step-count">01 — 03</div><h3>Choose your path</h3><div className="tab-row">{commands.map(([label],i)=><button onClick={()=>setActiveCommand(i)} className={activeCommand===i?'selected':''} key={label}>{label}</button>)}</div><CodeBlock label={commands[activeCommand][0].toLowerCase()}>{commands[activeCommand][1]}</CodeBlock><p className="tiny-note">For local backend work, create a virtual environment and install <code>requirements.txt</code> first.</p><a href="#usage" className="button button-wide">Continue to usage <ArrowRight size={16}/></a></div></section>

          <section id="usage" className="usage wrap"><div className="section-heading"><div className="eyebrow"><span></span> The workflow</div><h2>Turn a report into<br/>a clear next move.</h2></div><div className="flow"><article><span>01</span><Code2/><h3>A report arrives</h3><p>GitHub sends discussion or comment events into your n8n workflow.</p></article><ArrowRight className="flow-arrow"/><article><span>02</span><Bot/><h3>Turing investigates</h3><p>It builds a plan, inspects the live URL when configured, and looks for source context.</p></article><ArrowRight className="flow-arrow"/><article><span>03</span><Code2/><h3>Maintainers decide</h3><p>Get a report, correlation details, and optional changes to review before acting.</p></article></div><div className="usage-callout"><div><span className="label">USE IT IN ANY REPO</span><h3>One command. Your repository context.</h3><p>Install from an existing repository, or provide <code>owner/repo</code> explicitly.</p></div><CodeBlock label="bash">{installCommand + ' owner/repo'}</CodeBlock></div></section>

          <section id="api" className="api section-grid"><div><div className="eyebrow"><span></span> API surface</div><h2>Composable by<br/><em>design.</em></h2><p>Use Turing’s FastAPI endpoints from n8n or your own engineering workflow. Responses are structured to make a human review loop easy.</p><a href="/docs" className="text-link">Open local API docs <ArrowRight size={15}/></a></div><div className="endpoint-list">{endpoints.map(([method,path,description])=><article key={path}><div><span className="method">{method}</span><code>{path}</code></div><p>{description}</p><ChevronDown size={17}/></article>)}</div></section>

          <section className="limits wrap"><ShieldCheck size={24}/><div><span className="label">HUMAN-IN-THE-LOOP BY DEFAULT</span><h3>Useful automation without pretending certainty.</h3><p>Generated reports and patch proposals are suggestions—not proof that a bug has been reproduced, tested, or merged. Turing keeps the maintainer in control.</p></div></section>

          <footer><a className="brand" href="#top"><span className="brand-mark"><Bot size={19}/></span><span>TURING<span className="brand-dot">.</span></span></a><p>Autonomous QA, Git DAG defect timelines, and bug investigation for open-source maintainers.</p><div><a href="https://github.com/Turing-agent/Turing-agent">GitHub</a><a href="#dashboard" onClick={(e) => { e.preventDefault(); handleOpenDashboard(); }}>Dashboard</a><a href="#setup">Getting started</a><a href="#api">API</a></div></footer>
        </main>
      )}

      {/* GitHub Authentication Modal */}
      <GitHubAuthModal 
        isOpen={authModalOpen} 
        onClose={() => setAuthModalOpen(false)}
        onAuthenticated={(newAuth) => setAuthState(newAuth)}
        currentToken={authState.token}
      />
    </>
  )
}
createRoot(document.getElementById('root')).render(<App />)
