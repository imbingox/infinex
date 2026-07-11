import {
  AuditOutlined,
  DashboardOutlined,
  ExperimentOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlayCircleOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
} from "@ant-design/icons";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Flex,
  Layout,
  Menu,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import * as echarts from "echarts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { io } from "socket.io-client";

import { apiBaseUrl, apiRequest } from "./api";
import { statusTone } from "./status";
import type { AuditEvent, BacktestRun, Deployment, Strategy, Summary, Worker } from "./types";

const { Header, Content, Sider } = Layout;
type View = "overview" | "workers" | "strategies" | "backtests" | "deployments" | "audit";

const emptySummary: Summary = {
  workers: { total: 0, online: 0, degraded: 0, offline: 0 },
  strategies: { total: 0 },
  backtests: { total: 0, active: 0, succeeded: 0, failed: 0 },
  deployments: { total: 0, running: 0, failed: 0 },
};

function StatusTag({ value }: { value: string }) {
  return <Tag color={statusTone(value)}>{value.toUpperCase()}</Tag>;
}

function WorkerChart({ summary }: { summary: Summary }) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstanceRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = echarts.init(chartRef.current);
    chartInstanceRef.current = chart;
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
      chartInstanceRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartInstanceRef.current;
    if (!chart) return;
    chart.setOption({
      backgroundColor: "transparent",
      tooltip: { trigger: "item" },
      series: [
        {
          type: "pie",
          radius: ["58%", "82%"],
          label: { show: false },
          animationDurationUpdate: 300,
          data: [
            { value: summary.workers.online, name: "Online", itemStyle: { color: "#46d39a" } },
            { value: summary.workers.degraded, name: "Degraded", itemStyle: { color: "#f7b84b" } },
            { value: summary.workers.offline, name: "Offline", itemStyle: { color: "#ff6b74" } },
          ],
        },
      ],
    });
  }, [summary]);

  return <div ref={chartRef} className="worker-chart" />;
}

function Console() {
  const { message } = AntApp.useApp();
  const [view, setView] = useState<View>("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => window.localStorage.getItem("infinex.sidebarCollapsed") === "true",
  );
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string>();
  const [summary, setSummary] = useState<Summary>(emptySummary);
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [backtests, setBacktests] = useState<BacktestRun[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const requestInFlight = useRef(false);

  useEffect(() => {
    window.localStorage.setItem("infinex.sidebarCollapsed", String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const loadData = useCallback(async (mode: "initial" | "manual" | "background") => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    if (mode === "manual") setRefreshing(true);
    try {
      const [nextSummary, nextWorkers, nextStrategies, nextBacktests, nextDeployments, nextAudit] =
        await Promise.all([
          apiRequest<Summary>("/api/summary"),
          apiRequest<Worker[]>("/api/workers"),
          apiRequest<Strategy[]>("/api/strategies"),
          apiRequest<BacktestRun[]>("/api/backtests"),
          apiRequest<Deployment[]>("/api/deployments"),
          apiRequest<AuditEvent[]>("/api/audit-events?limit=50"),
        ]);
      setSummary(nextSummary);
      setWorkers(nextWorkers);
      setStrategies(nextStrategies);
      setBacktests(nextBacktests);
      setDeployments(nextDeployments);
      setAuditEvents(nextAudit);
      setError(undefined);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to load control-plane state");
    } finally {
      requestInFlight.current = false;
      if (mode === "initial") setInitialLoading(false);
      if (mode === "manual") setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void loadData("initial");
    const refreshTimer = window.setInterval(() => void loadData("background"), 5_000);
    const socket = io(apiBaseUrl || window.location.origin, { path: "/socket.io" });
    socket.on("system.updated", () => void loadData("background"));
    return () => {
      window.clearInterval(refreshTimer);
      socket.disconnect();
    };
  }, [loadData]);

  const deploymentAction = useCallback(
    async (deployment: Deployment) => {
      const action = deployment.desired_state === "running" ? "stop" : "start";
      try {
        await apiRequest(`/api/deployments/${deployment.id}/${action}`, { method: "POST" });
        message.success(`${deployment.name}: ${action} requested`);
        await loadData("background");
      } catch (cause) {
        message.error(cause instanceof Error ? cause.message : "Deployment action failed");
      }
    },
    [loadData, message],
  );

  const workerColumns: ColumnsType<Worker> = [
    { title: "Worker", dataIndex: "id" },
    { title: "Role", dataIndex: "role", render: (value: string) => <Tag>{value}</Tag> },
    { title: "Status", dataIndex: "status", render: (value: string) => <StatusTag value={value} /> },
    { title: "Runtime", dataIndex: "runtime_version" },
    {
      title: (
        <Space size={6}>
          Runner slots
          <Tooltip title="Active runners / configured concurrency limit">
            <QuestionCircleOutlined className="column-help" />
          </Tooltip>
        </Space>
      ),
      render: (_, item) => `${item.current_runs} / ${item.capacity}`,
    },
    { title: "Last heartbeat", dataIndex: "last_heartbeat_at", render: formatTime },
  ];

  const strategyColumns: ColumnsType<Strategy> = [
    { title: "Name", dataIndex: "name" },
    { title: "Owner", dataIndex: "owner", render: (value?: string) => value || "—" },
    { title: "Description", dataIndex: "description", render: (value?: string) => value || "—" },
    { title: "Created", dataIndex: "created_at", render: formatTime },
  ];

  const backtestColumns: ColumnsType<BacktestRun> = [
    { title: "Run", dataIndex: "id", ellipsis: true },
    { title: "Dataset", dataIndex: "dataset" },
    { title: "Status", dataIndex: "status", render: (value: string) => <StatusTag value={value} /> },
    { title: "Worker", dataIndex: "worker_id", render: (value?: string) => value || "—" },
    {
      title: "Return",
      render: (_, item) => {
        const value = item.result.metrics?.total_return;
        return value === undefined ? "—" : `${(value * 100).toFixed(2)}%`;
      },
    },
    { title: "Created", dataIndex: "created_at", render: formatTime },
  ];

  const deploymentColumns: ColumnsType<Deployment> = [
    { title: "Name", dataIndex: "name" },
    { title: "Worker", dataIndex: "worker_id" },
    {
      title: "Desired / Actual",
      render: (_, item) => (
        <Space>
          <StatusTag value={item.desired_state} />
          <span>→</span>
          <StatusTag value={item.actual_state} />
        </Space>
      ),
    },
    { title: "Revision", dataIndex: "desired_revision" },
    {
      title: "Action",
      render: (_, item) => (
        <Button size="small" onClick={() => void deploymentAction(item)}>
          {item.desired_state === "running" ? "Stop" : "Start"}
        </Button>
      ),
    },
  ];

  const auditColumns: ColumnsType<AuditEvent> = [
    { title: "Time", dataIndex: "created_at", render: formatTime },
    { title: "Actor", dataIndex: "actor" },
    { title: "Action", dataIndex: "action" },
    { title: "Object", render: (_, item) => `${item.object_type} / ${item.object_id}` },
  ];

  const page = useMemo(() => {
    if (view === "workers") {
      return <Table rowKey="id" loading={initialLoading} columns={workerColumns} dataSource={workers} />;
    }
    if (view === "strategies") {
      return <Table rowKey="id" loading={initialLoading} columns={strategyColumns} dataSource={strategies} />;
    }
    if (view === "backtests") {
      return <Table rowKey="id" loading={initialLoading} columns={backtestColumns} dataSource={backtests} />;
    }
    if (view === "deployments") {
      return <Table rowKey="id" loading={initialLoading} columns={deploymentColumns} dataSource={deployments} />;
    }
    if (view === "audit") {
      return <Table rowKey="id" loading={initialLoading} columns={auditColumns} dataSource={auditEvents} />;
    }
    return (
      <>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} xl={6}>
            <Card><Statistic title="Online workers" value={summary.workers.online} suffix={`/ ${summary.workers.total}`} /></Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card><Statistic title="Strategies" value={summary.strategies.total} /></Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card><Statistic title="Active backtests" value={summary.backtests.active} /></Card>
          </Col>
          <Col xs={24} sm={12} xl={6}>
            <Card><Statistic title="Running deployments" value={summary.deployments.running} /></Card>
          </Col>
        </Row>
        <Row gutter={[16, 16]} className="overview-row">
          <Col xs={24} lg={10}>
            <Card title="Worker health"><WorkerChart summary={summary} /></Card>
          </Col>
          <Col xs={24} lg={14}>
            <Card title="Recent workers">
              <Table rowKey="id" pagination={false} size="small" columns={workerColumns.slice(0, 5)} dataSource={workers.slice(0, 5)} />
            </Card>
          </Col>
        </Row>
      </>
    );
  }, [auditEvents, backtests, deployments, initialLoading, strategies, summary, view, workers]);

  return (
    <Layout className="shell">
      <Sider
        width={232}
        collapsedWidth={72}
        collapsed={sidebarCollapsed}
        trigger={null}
        className="sidebar"
      >
        <div className={`brand${sidebarCollapsed ? " brand-collapsed" : ""}`}>
          <span className="brand-mark">∞</span>
          <span className="brand-name">INFINEX</span>
        </div>
        <Tooltip title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} placement="right">
          <Button
            type="text"
            className="sidebar-toggle"
            aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            icon={sidebarCollapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setSidebarCollapsed((value) => !value)}
          />
        </Tooltip>
        <Menu
          theme="dark"
          mode="inline"
          inlineCollapsed={sidebarCollapsed}
          selectedKeys={[view]}
          onSelect={({ key }) => setView(key as View)}
          items={[
            { key: "overview", icon: <DashboardOutlined />, label: "Overview" },
            { key: "workers", icon: <RobotOutlined />, label: "Workers" },
            { key: "strategies", icon: <ExperimentOutlined />, label: "Strategies" },
            { key: "backtests", icon: <ExperimentOutlined />, label: "Backtests" },
            { key: "deployments", icon: <PlayCircleOutlined />, label: "Deployments" },
            { key: "audit", icon: <AuditOutlined />, label: "Audit" },
          ]}
        />
      </Sider>
      <Layout>
        <Header className="topbar">
          <Flex justify="space-between" align="center">
            <div>
              <Typography.Text className="eyebrow">CONTROL PLANE</Typography.Text>
              <Typography.Title level={3}>{view[0].toUpperCase() + view.slice(1)}</Typography.Title>
            </div>
            <Button
              icon={<ReloadOutlined />}
              loading={refreshing}
              onClick={() => void loadData("manual")}
            >
              Refresh
            </Button>
          </Flex>
        </Header>
        <Content className="content">
          {error && <Alert type="error" showIcon message="Control plane unavailable" description={error} className="error" />}
          {page}
        </Content>
      </Layout>
    </Layout>
  );
}

function formatTime(value?: string) {
  if (!value) return "—";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "medium" }).format(
    new Date(value),
  );
}

export default function App() {
  return <AntApp><Console /></AntApp>;
}
