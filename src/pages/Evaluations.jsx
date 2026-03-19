import { useState, useEffect } from 'react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

const Evaluations = () => {
    const [agent, setAgent] = useState('schedule')
    const [runs, setRuns] = useState(50)
    const [status, setStatus] = useState(null)
    const [runsList, setRunsList] = useState([])

    async function startEval() {
        setStatus('Starting...')
        try {
            const res = await fetch('/api/v1/automation/evaluate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ agent, runs, state_dim: 8 }),
            })
            const data = await res.json()
            setStatus(JSON.stringify(data))
        } catch (err) {
            setStatus('Error: ' + String(err))
        }
    }

    async function loadRuns() {
        try {
            const res = await fetch('/api/v1/evaluations/runs')
            const data = await res.json()
            setRunsList(data)
        } catch (err) {
            setStatus('Error loading runs: ' + String(err))
        }
    }

    useEffect(() => { loadRuns() }, [])

    // Alerts
    const [alerts, setAlerts] = useState([])
    const [alertForm, setAlertForm] = useState({ run_id: '', metric_key: '', operator: 'gt', threshold: 0, notify_url: '' })

    async function loadAlerts() {
        try {
            const res = await fetch('/api/v1/alerts/')
            const data = await res.json()
            setAlerts(data)
        } catch (err) {
            // ignore
        }
    }

    async function createAlert(e) {
        e.preventDefault()
        try {
            const res = await fetch('/api/v1/alerts/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(alertForm),
            })
            const data = await res.json()
            setAlertForm({ run_id: '', metric_key: '', operator: 'gt', threshold: 0, notify_url: '' })
            await loadAlerts()
            setStatus('Alert created: ' + data.id)
        } catch (err) {
            setStatus('Error creating alert: ' + String(err))
        }
    }

    async function deleteAlert(id) {
        try {
            await fetch('/api/v1/alerts/' + id, { method: 'DELETE' })
            await loadAlerts()
        } catch (err) {}
    }

    useEffect(() => { loadAlerts() }, [])

    return (
        <div className="p-6 ml-64">
            <h2 className="text-2xl font-semibold mb-4">Model & Agent Evaluations</h2>

            <div className="mb-4">
                <label className="block mb-2">Agent</label>
                <select value={agent} onChange={(e) => setAgent(e.target.value)} className="border p-2 rounded">
                    <option value="schedule">Schedule Agent</option>
                    <option value="reschedule">Reschedule Agent</option>
                </select>
            </div>

            <div className="mb-4">
                <label className="block mb-2">Runs</label>
                <input type="number" value={runs} onChange={(e) => setRuns(Number(e.target.value))} className="border p-2 rounded" />
            </div>

            <div className="flex items-center space-x-2 mb-6">
                <button onClick={startEval} className="bg-primary-600 text-white px-4 py-2 rounded">Start Evaluation</button>
                <button onClick={loadRuns} className="bg-gray-200 px-4 py-2 rounded">Refresh Runs</button>
                <a href="http://localhost:5000" target="_blank" rel="noreferrer" className="text-sm text-gray-600 underline">Open MLflow UI</a>
            </div>

            <div>
                <h3 className="font-medium mb-2">Runs</h3>
                {runsList.length === 0 && <div className="text-sm text-gray-500">No runs found.</div>}
                {runsList.map((r) => (
                    <div key={r.run_id} className="border rounded p-3 mb-3">
                        <div className="flex justify-between">
                            <div>
                                <div className="font-medium">Run: {r.run_id}</div>
                                <div className="text-xs text-gray-500">Experiment: {r.experiment_id} • Status: {r.status}</div>
                            </div>
                            <div className="text-right text-sm">
                                {r.metrics && Object.keys(r.metrics).map(k => (
                                    <div key={k}><strong>{k}:</strong> {String(r.metrics[k])}</div>
                                ))}
                            </div>
                        </div>

                        <div className="mt-3 grid grid-cols-2 gap-3">
                            {r.artifacts && r.artifacts.map((a) => (
                                <div key={a} className="p-1">
                                    {a.endsWith('.png') || a.endsWith('.jpg') ? (
                                        <img src={`/api/v1/evaluations/artifact/${r.run_id}/${encodeURIComponent(a)}`} alt={a} className="w-full h-auto rounded shadow" />
                                    ) : (
                                        <a href={`/api/v1/evaluations/artifact/${r.run_id}/${encodeURIComponent(a)}`} target="_blank" rel="noreferrer" className="text-sm text-blue-600 underline">{a}</a>
                                    )}
                                </div>
                            ))}
                        </div>

                        <div className="mt-3">
                            <h4 className="font-medium mb-2">Metric Histories</h4>
                            <div className="space-y-3">
                                {Object.keys(r.metrics || {}).slice(0,6).map((mk) => (
                                    <MetricChart key={mk} runId={r.run_id} metricKey={mk} />
                                ))}
                            </div>
                        </div>
                    </div>
                ))}
            </div>

            <div className="mt-6">
                <h3 className="font-medium">Status</h3>
                <pre className="bg-gray-100 p-4 rounded mt-2">{status}</pre>
            </div>

            <div className="mt-8">
                <h3 className="text-xl font-semibold mb-3">Alerts</h3>
                <form className="space-y-2 mb-4" onSubmit={createAlert}>
                    <div>
                        <input placeholder="Run ID" value={alertForm.run_id} onChange={(e)=>setAlertForm({...alertForm, run_id: e.target.value})} className="border p-2 rounded w-full" />
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                        <input placeholder="Metric Key" value={alertForm.metric_key} onChange={(e)=>setAlertForm({...alertForm, metric_key: e.target.value})} className="border p-2 rounded col-span-1" />
                        <select value={alertForm.operator} onChange={(e)=>setAlertForm({...alertForm, operator: e.target.value})} className="border p-2 rounded col-span-1">
                            <option value="gt">&gt;</option>
                            <option value="ge">&gt;=</option>
                            <option value="lt">&lt;</option>
                            <option value="le">&lt;=</option>
                        </select>
                        <input type="number" placeholder="Threshold" value={alertForm.threshold} onChange={(e)=>setAlertForm({...alertForm, threshold: Number(e.target.value)})} className="border p-2 rounded col-span-1" />
                    </div>
                    <div>
                        <input placeholder="Notify URL (optional webhook)" value={alertForm.notify_url} onChange={(e)=>setAlertForm({...alertForm, notify_url: e.target.value})} className="border p-2 rounded w-full" />
                    </div>
                    <div>
                        <button className="bg-primary-600 text-white px-4 py-2 rounded">Create Alert</button>
                    </div>
                </form>

                <div className="space-y-2">
                    {alerts.map(a=> (
                        <div key={a.id} className="border rounded p-2 flex justify-between items-center">
                            <div className="text-sm">{a.metric_key} {a.operator} {a.threshold} (run {a.run_id})</div>
                            <div>
                                <button onClick={()=>deleteAlert(a.id)} className="text-red-600">Delete</button>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}

export default Evaluations


function MetricChart({ runId, metricKey }) {
    const [data, setData] = useState(null)

    useEffect(() => {
        let mounted = true
        async function load() {
            try {
                const res = await fetch(`/api/v1/evaluations/metrics/${runId}/${encodeURIComponent(metricKey)}`)
                const json = await res.json()
                // convert timestamps to readable x-axis or step
                const points = json.map((p) => ({ x: p.step ?? p.timestamp, y: p.value }))
                if (mounted) setData(points)
            } catch (err) {
                // ignore
            }
        }
        load()
        return () => { mounted = false }
    }, [runId, metricKey])

    if (!data || data.length === 0) return <div className="text-sm text-gray-500">No history for {metricKey}</div>

    return (
        <div className="border rounded p-2">
            <div className="text-sm text-gray-700 mb-1">{metricKey}</div>
            <div style={{ width: '100%', height: 140 }}>
                <ResponsiveContainer>
                    <LineChart data={data}>
                        <XAxis dataKey="x" hide />
                        <YAxis />
                        <Tooltip />
                        <Line type="monotone" dataKey="y" stroke="#4f46e5" dot={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    )
}
