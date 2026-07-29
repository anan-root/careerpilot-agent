<script setup>
import { computed, onMounted, ref } from "vue";
import { apiGet, apiPost } from "./api";

const apiStatus = ref("连接中");
const busy = ref("");
const error = ref("");
const platforms = ref([]);
const selectedPlatforms = ref([]);
const jobs = ref([]);
const selectedJob = ref(null);
const searchSummary = ref(null);
const matchSummary = ref(null);

const searchForm = ref({
  keyword: "AI Agent",
  location: "上海",
  max_pages: 1,
  job_types: ["社招", "校招"],
  expand_keywords: true,
  enrich_details: false,
});

const importForm = ref({
  title: "",
  company: "",
  location: "",
  salary: "",
  url: "",
  jd_text: "",
  fetch_url: false,
});

const resumeText = ref("");

const topJobs = computed(() => (matchSummary.value?.top_jobs || []).slice(0, 5));
const platformCounts = computed(() => matchSummary.value?.platform_counts || searchSummary.value?.search_final_platform_counts || {});

onMounted(async () => {
  await loadMeta();
  await loadJobs();
});

async function loadMeta() {
  try {
    const [health, meta] = await Promise.all([
      apiGet("/health"),
      apiGet("/meta/platforms"),
    ]);
    apiStatus.value = health.status === "ok" ? "API 已连接" : "API 状态未知";
    platforms.value = meta.items || [];
    selectedPlatforms.value = meta.default || [];
  } catch (err) {
    apiStatus.value = "API 未连接";
    error.value = err.message;
  }
}

async function loadJobs() {
  try {
    const data = await apiGet("/jobs?limit=100");
    jobs.value = data.items || [];
    selectedJob.value = jobs.value[0] || null;
  } catch (err) {
    error.value = err.message;
  }
}

async function runSearch() {
  await withBusy("正在采集岗位", async () => {
    const data = await apiPost("/jobs/search", {
      ...searchForm.value,
      platforms: selectedPlatforms.value,
    });
    jobs.value = data.items || [];
    searchSummary.value = data.summary || null;
    matchSummary.value = null;
    selectedJob.value = jobs.value[0] || null;
  });
}

async function importJob() {
  await withBusy("正在导入岗位", async () => {
    const data = await apiPost("/jobs/import", importForm.value);
    if (data.job) {
      jobs.value = [data.job, ...jobs.value.filter((item) => item.id !== data.job.id)];
      selectedJob.value = data.job;
    }
    importForm.value.jd_text = "";
  });
}

async function matchResume() {
  if (!resumeText.value.trim()) {
    error.value = "请先粘贴简历文本";
    return;
  }
  await withBusy("正在匹配简历", async () => {
    const data = await apiPost("/jobs/match", {
      resume_text: resumeText.value,
      top_n: 20,
      ai_top_n: 0,
      job_types: ["社招", "校招", "实习"],
    });
    jobs.value = data.items || [];
    matchSummary.value = data.summary || null;
    selectedJob.value = jobs.value[0] || null;
  });
}

async function saveAction(type, job, status) {
  const path = type === "application" ? "/jobs/application" : type === "feedback" ? "/jobs/feedback" : "/jobs/bookmark";
  await withBusy("正在保存动作", async () => {
    await apiPost(path, {
      job_db_id: job.id || job.db_id || null,
      platform: job.platform || "",
      job_id: job.job_id || "",
      company: job.company || "",
      title: job.title || "",
      status,
      note: job.source_url || job.url || "",
      next_action: status === "已投递" ? "等待回复" : "",
    });
    await loadJobs();
  });
}

async function withBusy(label, callback) {
  busy.value = label;
  error.value = "";
  try {
    await callback();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = "";
  }
}

function togglePlatform(code) {
  const exists = selectedPlatforms.value.includes(code);
  selectedPlatforms.value = exists
    ? selectedPlatforms.value.filter((item) => item !== code)
    : [...selectedPlatforms.value, code];
}

function scoreOf(job) {
  return job?.resume_match?.score ?? job?.job_decision?.score ?? job?.score ?? "";
}

function levelOf(job) {
  return job?.resume_match?.level || job?.job_decision?.level || job?.match_level || "";
}
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">CareerPilot Workbench</p>
        <h1>岗位采集与简历匹配</h1>
      </div>
      <span class="status" :class="{ offline: apiStatus !== 'API 已连接' }">{{ apiStatus }}</span>
    </header>

    <section v-if="error" class="notice">{{ error }}</section>
    <section v-if="busy" class="notice muted">{{ busy }}</section>

    <div class="layout">
      <aside class="side">
        <section class="panel">
          <h2>多平台采集</h2>
          <label>关键词<input v-model="searchForm.keyword" /></label>
          <label>城市<input v-model="searchForm.location" /></label>
          <label>页数<input v-model.number="searchForm.max_pages" type="number" min="1" max="5" /></label>
          <div class="platforms">
            <button
              v-for="platform in platforms"
              :key="platform.code"
              type="button"
              :class="{ active: selectedPlatforms.includes(platform.code) }"
              @click="togglePlatform(platform.code)"
            >
              {{ platform.label }}
            </button>
          </div>
          <label class="check"><input v-model="searchForm.expand_keywords" type="checkbox" /> 扩展关键词</label>
          <label class="check"><input v-model="searchForm.enrich_details" type="checkbox" /> 抓取详情</label>
          <button class="primary" type="button" :disabled="!!busy" @click="runSearch">开始采集</button>
        </section>

        <section class="panel">
          <h2>岗位导入</h2>
          <label>岗位<input v-model="importForm.title" /></label>
          <label>公司<input v-model="importForm.company" /></label>
          <label>城市<input v-model="importForm.location" /></label>
          <label>薪资<input v-model="importForm.salary" /></label>
          <label>链接<input v-model="importForm.url" /></label>
          <textarea v-model="importForm.jd_text" rows="5" placeholder="粘贴 JD 文本"></textarea>
          <label class="check"><input v-model="importForm.fetch_url" type="checkbox" /> 尝试读取链接正文</label>
          <button type="button" :disabled="!!busy" @click="importJob">导入岗位</button>
        </section>

        <section class="panel">
          <h2>简历匹配</h2>
          <textarea v-model="resumeText" rows="8" placeholder="粘贴简历文本"></textarea>
          <button class="primary" type="button" :disabled="!!busy" @click="matchResume">匹配简历</button>
        </section>
      </aside>

      <section class="content">
        <div class="metrics">
          <article>
            <span>岗位数</span>
            <strong>{{ jobs.length }}</strong>
          </article>
          <article>
            <span>平均分</span>
            <strong>{{ matchSummary?.avg_score || 0 }}</strong>
          </article>
          <article>
            <span>强匹配</span>
            <strong>{{ matchSummary?.high_match_count || 0 }}</strong>
          </article>
          <article>
            <span>字段质量</span>
            <strong>{{ matchSummary?.avg_field_quality || searchSummary?.search_job_quality?.avg_score || 0 }}</strong>
          </article>
        </div>

        <section class="board">
          <div>
            <h2>推荐 Top 岗位</h2>
            <div v-if="topJobs.length" class="top-list">
              <button v-for="item in topJobs" :key="`${item.rank}-${item.company}-${item.title}`" type="button">
                <span>{{ item.rank }}. {{ item.company }}</span>
                <strong>{{ item.score }}</strong>
              </button>
            </div>
            <p v-else class="empty">完成简历匹配后显示推荐摘要。</p>
          </div>
          <div>
            <h2>平台分布</h2>
            <div class="chips">
              <span v-for="(count, name) in platformCounts" :key="name">{{ name }} {{ count }}</span>
            </div>
          </div>
        </section>

        <section class="jobs">
          <article
            v-for="job in jobs"
            :key="`${job.platform}-${job.job_id}-${job.id}`"
            class="job-card"
            :class="{ selected: selectedJob === job }"
            @click="selectedJob = job"
          >
            <div>
              <span class="source">{{ job.platform || "manual" }}</span>
              <h3>{{ job.title || "未命名岗位" }}</h3>
              <p>{{ job.company || "未知公司" }} · {{ job.location || "地点待确认" }} · {{ job.salary || "薪资待确认" }}</p>
            </div>
            <div class="score">
              <strong>{{ scoreOf(job) }}</strong>
              <span>{{ levelOf(job) }}</span>
            </div>
            <p class="desc">{{ job.description || job.requirements || job.full_jd || "暂无 JD 摘要" }}</p>
            <div class="actions">
              <button type="button" @click.stop="saveAction('bookmark', job, '收藏')">收藏</button>
              <button type="button" @click.stop="saveAction('feedback', job, '不合适')">不合适</button>
              <button type="button" @click.stop="saveAction('application', job, '已投递')">已投递</button>
              <a v-if="job.source_url || job.url" :href="job.source_url || job.url" target="_blank" rel="noreferrer">来源</a>
            </div>
          </article>
          <p v-if="!jobs.length" class="empty">暂无岗位。</p>
        </section>
      </section>
    </div>
  </main>
</template>
