/*
 * manet-routing.cc
 *
 * Avaliacao de mobilidade e roteamento em uma MANET no ns-3.
 * Trabalho final de Redes Moveis, Engenharia de Software, IFG Campus Inhumas, 2026/2.
 *
 * Um unico programa cobre os tres protocolos (AODV, OLSR e DSDV). Tudo que varia
 * entre execucoes e argumento de linha de comando, entao o lote completo roda
 * sem editar nem recompilar o codigo.
 *
 * Etapas (mesma ordem dos slides da disciplina):
 *   1. ler parametros            5. instalar pilha IP + roteamento
 *   2. criar nos                 6. criar trafego UDP
 *   3. configurar mobilidade     7. instalar FlowMonitor
 *   4. configurar Wi-Fi Ad Hoc   8. executar e exportar CSV
 *
 * Exemplo:
 *   ./ns3 run "scratch/manet-routing --protocol=AODV --speed=10 --run=3 --simTime=120"
 */

#include "ns3/aodv-module.h"
#include "ns3/applications-module.h"
#include "ns3/core-module.h"
#include "ns3/dsdv-module.h"
#include "ns3/flow-monitor-module.h"
#include "ns3/internet-module.h"
#include "ns3/mobility-module.h"
#include "ns3/network-module.h"
#include "ns3/olsr-module.h"
#include "ns3/wifi-module.h"

#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <map>
#include <string>
#include <vector>

using namespace ns3;

NS_LOG_COMPONENT_DEFINE("ManetRouting");

namespace
{

// Porta UDP do primeiro fluxo de dados. O fluxo i usa a porta DATA_PORT_BASE + i,
// o que permite identificar cada fluxo no FlowMonitor sem ambiguidade.
const uint16_t DATA_PORT_BASE = 9000;

// Pacotes gerados pela aplicacao em cada fluxo (contados na origem, antes do socket).
std::vector<uint64_t> g_appTxPackets;

/**
 * Callback do trace "Tx" do UdpClient. O trace dispara para todo pacote gerado,
 * inclusive quando o socket recusa o envio por falta de rota.
 */
void
AppTxTrace(uint32_t flowIndex, Ptr<const Packet> /* packet */)
{
    g_appTxPackets[flowIndex]++;
}

// Mensagens de controle do roteamento transmitidas por todos os nos da rede.
uint64_t g_ctrlTxPackets = 0;
uint64_t g_ctrlTxBytes = 0;

/**
 * Callback do trace "Tx" do Ipv4L3Protocol, que dispara para todo pacote IP entregue
 * a interface Wi-Fi. Conta os pacotes UDP destinados a porta do protocolo de roteamento.
 * O FlowMonitor nao serve para isso porque ignora pacotes em broadcast.
 */
void
Ipv4TxTrace(uint16_t controlPort,
            Ptr<const Packet> packet,
            Ptr<Ipv4> /* ipv4 */,
            uint32_t /* interface */)
{
    Ptr<Packet> copy = packet->Copy();
    Ipv4Header ip;
    copy->RemoveHeader(ip);
    if (ip.GetProtocol() != UdpL4Protocol::PROT_NUMBER)
    {
        return;
    }
    UdpHeader udp;
    copy->PeekHeader(udp);
    if (udp.GetDestinationPort() == controlPort)
    {
        g_ctrlTxPackets++;
        g_ctrlTxBytes += packet->GetSize(); // inclui cabecalhos IP e UDP
    }
}

/** Grava a posicao de todos os nos e reagenda a si mesma. */
void
LogPositions(Ptr<OutputStreamWrapper> stream, NodeContainer nodes, Time interval)
{
    std::ostream* os = stream->GetStream();
    for (uint32_t i = 0; i < nodes.GetN(); ++i)
    {
        Vector p = nodes.Get(i)->GetObject<MobilityModel>()->GetPosition();
        *os << std::fixed << std::setprecision(3) << Simulator::Now().GetSeconds() << "," << i
            << "," << p.x << "," << p.y << "\n";
    }
    Simulator::Schedule(interval, &LogPositions, stream, nodes, interval);
}

/** Estatisticas acumuladas de um fluxo de dados. */
struct FlowResult
{
    uint32_t srcNode{0};
    uint32_t dstNode{0};
    uint16_t dstPort{0};
    uint64_t appTxPackets{0}; // gerados pela aplicacao
    uint64_t ipTxPackets{0};  // vistos pelo FlowMonitor na camada IP da origem
    uint64_t rxPackets{0};
    uint64_t rxBytes{0};
    uint64_t timesForwarded{0};
    double delaySumS{0.0};
    double jitterSumS{0.0};
    double timeFirstTxS{std::numeric_limits<double>::quiet_NaN()};
    double timeLastRxS{std::numeric_limits<double>::quiet_NaN()};
};

} // namespace

int
main(int argc, char* argv[])
{
    // ------------------------------------------------------------------
    // 1. Parametros
    // ------------------------------------------------------------------
    std::string protocol = "AODV"; // AODV | OLSR | DSDV
    double speed = 10.0;           // m/s, velocidade constante dos nos
    uint32_t run = 1;              // repeticao independente (RngRun)
    uint32_t seed = 12345;         // seed mestre, fixa
    double simTime = 120.0;        // s
    uint32_t nNodes = 20;
    uint32_t nFlows = 4;
    double areaSide = 500.0;  // m, area quadrada areaSide x areaSide
    double pause = 0.0;       // s, tempo de pausa do Random Waypoint
    uint32_t pktSize = 1024;  // bytes de carga UDP
    double packetRate = 20.0; // pacotes/s por fluxo
    double txPower = 4.0;     // dBm, alcance de aproximadamente 197 m (ver README)
    double appStart = 20.0;   // s, inicio do trafego (aquecimento antes disso)
    double appStop = -1.0;    // s, fim do trafego; negativo = simTime - 10
    double arpDeadTimeout = 1.0; // s, bloqueio do ARP apos falha (padrao do ns-3: 100)
    double lineSpacing = 0.0; // m; > 0 ativa o modo de validacao (nos parados em linha)
    std::string csvFile;      // CSV de saida (uma linha por fluxo)
    std::string mobilityTraceFile;
    std::string flowmonXmlFile;
    bool quiet = false;

    CommandLine cmd(__FILE__);
    cmd.AddValue("protocol", "Protocolo de roteamento: AODV, OLSR ou DSDV", protocol);
    cmd.AddValue("speed", "Velocidade dos nos (m/s)", speed);
    cmd.AddValue("run", "Numero da repeticao (RngRun)", run);
    cmd.AddValue("seed", "Seed mestre do gerador pseudoaleatorio", seed);
    cmd.AddValue("simTime", "Tempo de simulacao (s)", simTime);
    cmd.AddValue("nodes", "Quantidade de nos", nNodes);
    cmd.AddValue("flows", "Fluxos UDP simultaneos", nFlows);
    cmd.AddValue("area", "Lado da area quadrada (m)", areaSide);
    cmd.AddValue("pause", "Tempo de pausa do Random Waypoint (s)", pause);
    cmd.AddValue("pktSize", "Carga UDP por pacote (bytes)", pktSize);
    cmd.AddValue("packetRate", "Pacotes por segundo em cada fluxo", packetRate);
    cmd.AddValue("txPower", "Potencia de transmissao (dBm)", txPower);
    cmd.AddValue("appStart", "Inicio do trafego (s)", appStart);
    cmd.AddValue("appStop", "Fim do trafego (s); negativo usa simTime - 10", appStop);
    cmd.AddValue("arpDeadTimeout",
                 "Tempo em que o ARP ignora um vizinho apos falhar a resolucao (s)",
                 arpDeadTimeout);
    cmd.AddValue("lineSpacing",
                 "Validacao: se > 0, nos parados em linha com este espacamento (m)",
                 lineSpacing);
    cmd.AddValue("csv", "Arquivo CSV de saida (uma linha por fluxo)", csvFile);
    cmd.AddValue("mobilityTrace", "Arquivo CSV com a posicao dos nos a cada 1 s", mobilityTraceFile);
    cmd.AddValue("flowmonXml", "Arquivo XML bruto do FlowMonitor", flowmonXmlFile);
    cmd.AddValue("quiet", "Nao imprime o resumo no terminal", quiet);
    cmd.Parse(argc, argv);

    if (appStop < 0.0)
    {
        appStop = simTime - 10.0;
    }
    const bool lineMode = lineSpacing > 0.0;

    NS_ABORT_MSG_IF(protocol != "AODV" && protocol != "OLSR" && protocol != "DSDV",
                    "Protocolo invalido: " << protocol << " (use AODV, OLSR ou DSDV)");
    NS_ABORT_MSG_IF(nNodes < 2, "Sao necessarios pelo menos 2 nos");
    NS_ABORT_MSG_IF(nFlows < 1, "E necessario pelo menos 1 fluxo");
    NS_ABORT_MSG_IF(!lineMode && 2 * nFlows > nNodes,
                    "Cada fluxo usa origem e destino exclusivos: flows deve ser <= nodes/2");
    NS_ABORT_MSG_IF(appStop <= appStart || appStop > simTime,
                    "Janela de trafego invalida: use appStart < appStop <= simTime");
    NS_ABORT_MSG_IF(speed <= 0.0 && !lineMode, "A velocidade deve ser positiva");
    NS_ABORT_MSG_IF(pktSize < 12, "pktSize minimo e 12 bytes (cabecalho do UdpClient)");

    // Duracao util: e a mesma para todos os fluxos, protocolos e repeticoes.
    const double trafficDuration = appStop - appStart;
    const Time packetInterval = Seconds(1.0 / packetRate);

    // Ajuste do ARP (justificativa completa no README). No padrao do ns-3, um vizinho que
    // nao responde aos pedidos ARP fica marcado como morto por 100 s e todo pacote enviado
    // a ele e descartado em silencio, sem avisar o protocolo de roteamento. Em 120 s de
    // simulacao com nos moveis isso vira um "buraco negro" que dura quase a execucao toda
    // e nao tem relacao com os protocolos avaliados. Com 1 s, a resolucao e tentada de novo.
    Config::SetDefault("ns3::ArpCache::DeadTimeout", TimeValue(Seconds(arpDeadTimeout)));

    // Seed mestre fixa e run variando: repeticoes independentes e reprodutiveis.
    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(run);

    // ------------------------------------------------------------------
    // 2. Nos
    // ------------------------------------------------------------------
    NodeContainer nodes;
    nodes.Create(nNodes);

    // ------------------------------------------------------------------
    // 3. Mobilidade
    // ------------------------------------------------------------------
    // Os streams aleatorios da mobilidade sao fixados explicitamente (indices 0, 1, 2...).
    // Sem isso o ns-3 distribui streams pela ordem de criacao dos objetos, que muda de
    // um protocolo para outro. Com os streams fixos, a mesma combinacao de seed, run,
    // velocidade e numero de nos produz exatamente as mesmas trajetorias para AODV,
    // OLSR e DSDV, que e a condicao para a comparacao entre protocolos ser justa.
    MobilityHelper mobility;
    int64_t stream = 0;

    if (lineMode)
    {
        Ptr<ListPositionAllocator> line = CreateObject<ListPositionAllocator>();
        for (uint32_t i = 0; i < nNodes; ++i)
        {
            line->Add(Vector(i * lineSpacing, 0.0, 0.0));
        }
        mobility.SetPositionAllocator(line);
        mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
        mobility.Install(nodes);
    }
    else
    {
        std::ostringstream coord;
        coord << "ns3::UniformRandomVariable[Min=0.0|Max=" << areaSide << "]";
        ObjectFactory pos;
        pos.SetTypeId("ns3::RandomRectanglePositionAllocator");
        pos.Set("X", StringValue(coord.str()));
        pos.Set("Y", StringValue(coord.str()));
        Ptr<PositionAllocator> positionAlloc = pos.Create()->GetObject<PositionAllocator>();
        stream += positionAlloc->AssignStreams(stream);

        std::ostringstream speedVar;
        speedVar << "ns3::ConstantRandomVariable[Constant=" << speed << "]";
        std::ostringstream pauseVar;
        pauseVar << "ns3::ConstantRandomVariable[Constant=" << pause << "]";

        // O mesmo alocador sorteia a posicao inicial e os destinos (waypoints).
        mobility.SetPositionAllocator(positionAlloc);
        mobility.SetMobilityModel("ns3::RandomWaypointMobilityModel",
                                  "Speed",
                                  StringValue(speedVar.str()),
                                  "Pause",
                                  StringValue(pauseVar.str()),
                                  "PositionAllocator",
                                  PointerValue(positionAlloc));
        mobility.Install(nodes);
        stream += mobility.AssignStreams(nodes, stream);
    }

    // ------------------------------------------------------------------
    // 4. Wi-Fi IEEE 802.11b em modo Ad Hoc
    // ------------------------------------------------------------------
    // Dados, controle e broadcast usam a mesma taxa (11 Mbps). Assim o alcance das
    // mensagens de roteamento (broadcast) e igual ao alcance dos dados (unicast), e
    // nenhum protocolo "enxerga" vizinhos que depois nao consegue usar.
    const std::string phyMode = "DsssRate11Mbps";
    Config::SetDefault("ns3::WifiRemoteStationManager::NonUnicastMode", StringValue(phyMode));

    WifiHelper wifi;
    wifi.SetStandard(WIFI_STANDARD_80211b);
    wifi.SetRemoteStationManager("ns3::ConstantRateWifiManager",
                                 "DataMode",
                                 StringValue(phyMode),
                                 "ControlMode",
                                 StringValue(phyMode));

    YansWifiChannelHelper channel;
    channel.SetPropagationDelay("ns3::ConstantSpeedPropagationDelayModel");
    // Espaco livre (Friis) na frequencia do canal 1 de 2,4 GHz.
    channel.AddPropagationLoss("ns3::FriisPropagationLossModel", "Frequency", DoubleValue(2.412e9));

    YansWifiPhyHelper phy;
    phy.SetChannel(channel.Create());
    phy.Set("TxPowerStart", DoubleValue(txPower));
    phy.Set("TxPowerEnd", DoubleValue(txPower));

    WifiMacHelper mac;
    mac.SetType("ns3::AdhocWifiMac");
    NetDeviceContainer devices = wifi.Install(phy, mac, nodes);

    // ------------------------------------------------------------------
    // 5. Pilha IP e protocolo de roteamento
    // ------------------------------------------------------------------
    // Os tres protocolos usam os parametros padrao do ns-3.
    InternetStackHelper internet;
    uint16_t controlPort = 0; // porta UDP das mensagens de controle do protocolo
    if (protocol == "AODV")
    {
        AodvHelper aodv;
        internet.SetRoutingHelper(aodv);
        controlPort = 654;
    }
    else if (protocol == "OLSR")
    {
        OlsrHelper olsr;
        internet.SetRoutingHelper(olsr);
        controlPort = 698;
    }
    else // DSDV
    {
        DsdvHelper dsdv;
        internet.SetRoutingHelper(dsdv);
        controlPort = 269;
    }
    internet.Install(nodes);

    Ipv4AddressHelper address;
    address.SetBase("10.1.1.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    // Custo de controle: conta as mensagens do protocolo de roteamento em todos os nos.
    Config::ConnectWithoutContext("/NodeList/*/$ns3::Ipv4L3Protocol/Tx",
                                  MakeBoundCallback(&Ipv4TxTrace, controlPort));

    // Confirma qual protocolo foi de fato instalado (vai para o terminal e para o CSV).
    const std::string routingTypeId =
        nodes.Get(0)->GetObject<Ipv4>()->GetRoutingProtocol()->GetInstanceTypeId().GetName();

    // ------------------------------------------------------------------
    // 6. Trafego UDP de taxa constante
    // ------------------------------------------------------------------
    // Fluxo i: no i -> no (N - 1 - i). Origens e destinos nao se repetem e sao os
    // mesmos para todos os protocolos. No modo de validacao em linha, todos os fluxos
    // vao de uma ponta a outra (no 0 -> no N - 1).
    std::vector<FlowResult> results(nFlows);
    g_appTxPackets.assign(nFlows, 0);

    // Cada fluxo comeca com um atraso sorteado entre 0 e 1 s, para as fontes nao
    // transmitirem em fase. O stream e fixo: os atrasos sao os mesmos para os tres
    // protocolos. A duracao do trafego e identica em todos os fluxos.
    Ptr<UniformRandomVariable> startOffset = CreateObject<UniformRandomVariable>();
    startOffset->SetStream(stream++);

    for (uint32_t i = 0; i < nFlows; ++i)
    {
        const uint32_t src = lineMode ? 0 : i;
        const uint32_t dst = lineMode ? nNodes - 1 : nNodes - 1 - i;
        const uint16_t port = DATA_PORT_BASE + i;
        results[i].srcNode = src;
        results[i].dstNode = dst;
        results[i].dstPort = port;

        const Time offset = Seconds(startOffset->GetValue(0.0, 1.0));

        UdpServerHelper server(port);
        ApplicationContainer serverApp = server.Install(nodes.Get(dst));
        serverApp.Start(Seconds(0.0));
        serverApp.Stop(Seconds(simTime));

        UdpClientHelper client(interfaces.GetAddress(dst), port);
        client.SetAttribute("MaxPackets", UintegerValue(0)); // 0 = sem limite
        client.SetAttribute("Interval", TimeValue(packetInterval));
        client.SetAttribute("PacketSize", UintegerValue(pktSize));
        ApplicationContainer clientApp = client.Install(nodes.Get(src));
        clientApp.Start(Seconds(appStart) + offset);
        clientApp.Stop(Seconds(appStop) + offset);
        clientApp.Get(0)->TraceConnectWithoutContext("Tx", MakeBoundCallback(&AppTxTrace, i));
    }

    // ------------------------------------------------------------------
    // 7. FlowMonitor
    // ------------------------------------------------------------------
    FlowMonitorHelper flowmonHelper;
    Ptr<FlowMonitor> monitor = flowmonHelper.InstallAll();

    if (!mobilityTraceFile.empty())
    {
        AsciiTraceHelper ascii;
        Ptr<OutputStreamWrapper> mobStream = ascii.CreateFileStream(mobilityTraceFile);
        *mobStream->GetStream() << "timeS,node,x,y\n";
        Simulator::Schedule(Seconds(0.0), &LogPositions, mobStream, nodes, Seconds(1.0));
    }

    // ------------------------------------------------------------------
    // 8. Execucao e coleta
    // ------------------------------------------------------------------
    Simulator::Stop(Seconds(simTime));
    Simulator::Run();

    monitor->CheckForLostPackets();
    Ptr<Ipv4FlowClassifier> classifier =
        DynamicCast<Ipv4FlowClassifier>(flowmonHelper.GetClassifier());

    for (const auto& [flowId, st] : monitor->GetFlowStats())
    {
        const Ipv4FlowClassifier::FiveTuple t = classifier->FindFlow(flowId);
        // Somente os fluxos de dados interessam aqui. O FlowMonitor tambem registra as
        // mensagens unicast do roteamento (RREP do AODV, por exemplo), que sao descartadas.
        if (t.protocol != UdpL4Protocol::PROT_NUMBER)
        {
            continue;
        }
        if (t.destinationPort < DATA_PORT_BASE || t.destinationPort >= DATA_PORT_BASE + nFlows)
        {
            continue;
        }
        FlowResult& r = results[t.destinationPort - DATA_PORT_BASE];
        r.ipTxPackets += st.txPackets;
        r.rxPackets += st.rxPackets;
        r.rxBytes += st.rxBytes;
        r.timesForwarded += st.timesForwarded;
        r.delaySumS += st.delaySum.GetSeconds();
        r.jitterSumS += st.jitterSum.GetSeconds();
        if (st.txPackets > 0)
        {
            r.timeFirstTxS = st.timeFirstTxPacket.GetSeconds();
        }
        if (st.rxPackets > 0)
        {
            r.timeLastRxS = st.timeLastRxPacket.GetSeconds();
        }
    }

    if (!flowmonXmlFile.empty())
    {
        monitor->SerializeToXmlFile(flowmonXmlFile, false, false);
    }

    // Metricas por fluxo.
    //   throughput = rxBytes * 8 / duracao util, com duracao util = appStop - appStart.
    //                rxBytes vem do FlowMonitor e inclui os cabecalhos IP e UDP (28 bytes).
    //   PDR        = rxPackets / pacotes gerados pela aplicacao * 100.
    //                O denominador e contado na aplicacao porque o OLSR recusa o envio no
    //                socket quando nao ha rota: esses pacotes nunca chegam a camada IP e o
    //                FlowMonitor nao os contaria como transmitidos, o que inflaria o PDR.
    //   delay      = delaySum / rxPackets.
    //   jitter     = jitterSum / (rxPackets - 1).
    const double nan = std::numeric_limits<double>::quiet_NaN();
    std::ostringstream rows;
    rows << std::fixed << std::setprecision(6);

    uint64_t totalAppTx = 0;
    uint64_t totalRx = 0;
    uint64_t totalRxBytes = 0;
    double totalDelay = 0.0;
    double totalJitter = 0.0;
    uint64_t totalJitterSamples = 0;

    if (!quiet)
    {
        std::cout << "protocolo=" << protocol << " (" << routingTypeId << ") velocidade=" << speed
                  << " m/s nos=" << nNodes << " fluxos=" << nFlows << " seed=" << seed
                  << " run=" << run << "\n";
    }

    for (uint32_t i = 0; i < nFlows; ++i)
    {
        FlowResult& r = results[i];
        r.appTxPackets = g_appTxPackets[i];

        const uint64_t lost = r.appTxPackets - r.rxPackets;
        const double throughputMbps = r.rxBytes * 8.0 / trafficDuration / 1e6;
        const double pdrPct = r.appTxPackets > 0 ? 100.0 * r.rxPackets / r.appTxPackets : nan;
        const double delayMs = r.rxPackets > 0 ? 1e3 * r.delaySumS / r.rxPackets : nan;
        const double jitterMs = r.rxPackets > 1 ? 1e3 * r.jitterSumS / (r.rxPackets - 1) : nan;
        const double avgHops =
            r.rxPackets > 0 ? 1.0 + static_cast<double>(r.timesForwarded) / r.rxPackets : nan;

        totalAppTx += r.appTxPackets;
        totalRx += r.rxPackets;
        totalRxBytes += r.rxBytes;
        totalDelay += r.delaySumS;
        totalJitter += r.jitterSumS;
        totalJitterSamples += r.rxPackets > 1 ? r.rxPackets - 1 : 0;

        rows << protocol << "," << speed << "," << nNodes << "," << nFlows << "," << areaSide << ","
             << pause << "," << pktSize << "," << packetRate << "," << txPower << ","
             << arpDeadTimeout << "," << simTime
             << "," << appStart << "," << appStop << "," << seed << "," << run << "," << (i + 1)
             << "," << r.srcNode << "," << r.dstNode << "," << r.dstPort << "," << r.appTxPackets
             << "," << r.ipTxPackets << "," << r.rxPackets << "," << lost << "," << r.rxBytes << ","
             << throughputMbps << "," << pdrPct << "," << delayMs << "," << jitterMs << ","
             << r.timesForwarded << "," << avgHops << "," << r.timeFirstTxS << "," << r.timeLastRxS
             << "," << g_ctrlTxPackets << "," << g_ctrlTxBytes << "," << routingTypeId << "\n";

        if (!quiet)
        {
            std::cout << "  fluxo " << (i + 1) << " (no " << r.srcNode << " -> no " << r.dstNode
                      << "): gerados=" << r.appTxPackets << " recebidos=" << r.rxPackets
                      << " perdidos=" << lost << std::fixed << std::setprecision(2)
                      << " PDR=" << pdrPct << "% vazao=" << std::setprecision(4) << throughputMbps
                      << " Mbps atraso=" << std::setprecision(2) << delayMs
                      << " ms jitter=" << jitterMs << " ms saltos~" << avgHops << "\n";
        }
    }

    if (!csvFile.empty())
    {
        std::ofstream out(csvFile);
        NS_ABORT_MSG_IF(!out.is_open(), "Nao foi possivel abrir " << csvFile);
        out << "protocol,speed,nodes,flows,areaSide,pause,pktSize,packetRate,txPowerDbm,"
               "arpDeadTimeout,simTime,"
               "appStart,appStop,seed,run,flowId,srcNode,dstNode,dstPort,appTxPackets,ipTxPackets,"
               "rxPackets,lostPackets,rxBytes,throughputMbps,pdrPct,delayMs,jitterMs,"
               "timesForwarded,avgHops,timeFirstTxS,timeLastRxS,runCtrlTxPackets,runCtrlTxBytes,"
               "routingTypeId\n";
        out << rows.str();
    }

    if (!quiet)
    {
        std::cout << std::fixed << std::setprecision(2);
        std::cout << "  REDE: gerados=" << totalAppTx << " recebidos=" << totalRx
                  << " PDR=" << (totalAppTx > 0 ? 100.0 * totalRx / totalAppTx : nan)
                  << "% vazao=" << std::setprecision(4)
                  << totalRxBytes * 8.0 / trafficDuration / 1e6 << " Mbps atraso="
                  << std::setprecision(2) << (totalRx > 0 ? 1e3 * totalDelay / totalRx : nan)
                  << " ms jitter="
                  << (totalJitterSamples > 0 ? 1e3 * totalJitter / totalJitterSamples : nan)
                  << " ms controle=" << g_ctrlTxPackets << " pacotes (" << g_ctrlTxBytes << " bytes)\n";
    }

    Simulator::Destroy();
    return 0;
}
