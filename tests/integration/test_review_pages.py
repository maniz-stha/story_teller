import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from story_teller.app import create_app


def test_review_page_exposes_workflow_controls(tmp_path: Path):
    response = TestClient(create_app(tmp_path)).get("/")
    assert response.status_code == 200
    for label in ("Upload clip", "Generate video", "Story feedback", "Subtitle position", "Approve", "Download"):
        assert label in response.text


def test_failed_story_is_loaded_after_queued_state():
    script = r"""
const fs = require('fs'); const vm = require('vm'); const assert = require('assert');
const source = fs.readFileSync('src/story_teller/static/app.js','utf8').split('Promise.all([request')[0];
const elements = new Map();
function element(id) { if (!elements.has(id)) elements.set(id,{textContent:'',value:'',replaceChildren(){},querySelectorAll(){return []}}); return elements.get(id); }
let status = 'queued';
const context = vm.createContext({document:{querySelector:element},Option:function(label,value){return {label,value}},setInterval(){},fetch:async url=>({ok:true,status:200,json:async()=>url.endsWith('/revisions/1') ? {story:status==='failed'?'I found a secret':null,summary:'A clue was resolved.',model_info:{story_title:'The clue',word_count:390,estimated_duration_seconds:90},evaluation:status==='failed'?{reasons:['Too short']}:null,posting_copy:null} : url.endsWith('/runs/r') ? {status,revisions:[{number:1}],error:status==='failed'?'evaluating failed':null,approved_revision_id:null} : []})});
vm.runInContext(source,context); vm.runInContext("currentRun='r'",context);
(async()=>{await vm.runInContext('refresh()',context); status='failed'; await vm.runInContext('refresh()',context); assert.equal(element('#story').textContent,'I found a secret'); assert.equal(element('#story-title').textContent,'The clue'); assert.match(element('#story-meta').textContent,/390 words/); assert.equal(element('#continuity-note').textContent,'A clue was resolved.'); assert.match(element('#evaluation').textContent,/Too short/);})().catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run(["node", "-e", script], check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_review_page_has_story_output_fields(tmp_path: Path):
    html = TestClient(create_app(tmp_path)).get("/").text
    assert 'id="story-title"' in html
    assert 'id="story-meta"' in html
    assert 'id="continuity-note"' in html
