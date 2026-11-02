#include "mm/fmm/ubodt.hpp"
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <sys/stat.h>
#include <cerrno>
#include <fstream>
#include <cstdio>
#include <limits>
#include <boost/archive/binary_oarchive.hpp>
using FMM::MM::UBODT;
using FMM::MM::Record;
static void put(UBODT &table, int source, int target, int next, int edge) {
  auto r = static_cast<Record *>(std::calloc(1, sizeof(Record)));
  r->source=source; r->target=target; r->first_n=next; r->next_e=edge; r->cost=1;
  table.insert(r);
}
static void require(bool ok) { if (!ok) throw std::runtime_error("test failed"); }
int main(int argc, char **argv) {
  if (argc == 2 && std::string(argv[1]) == "--parser") {
    const std::string name = "ubodt_parser_isolated_test.csv";
    const char *bad[] = {"-1;2;2;1;1;1", "1;2;2;-1;1;1",
      "4294967296;2;2;1;1;1", "9223372036854775808;2;2;1;1;1",
      "1;2;2;1;1;nan", "1;2;2;1;1;inf", "1;2;2;1;1;-1",
      "1;2;2;1;1;1;extra", "1;2;2;1;1;1junk", "1;2"};
    for (auto row : bad) {
      { std::ofstream out(name); out << "header\n" << row << "\n"; }
      bool rejected = false;
      try { UBODT::read_ubodt_csv(name, 50000); }
      catch (const std::runtime_error &) { rejected = true; }
      require(rejected);
    }
    { std::ofstream out(name); out << "header\n1;2;2;1;1;1000\n"; }
    require(UBODT::read_ubodt_csv(name, 50000)->look_up(1,2)->cost == 1000);
    std::remove(name.c_str());
    const std::string bin = "ubodt_parser_isolated_test.bin";
    for (double cost : {1.0, -1.0, std::numeric_limits<double>::infinity()}) {
      { std::ofstream out(bin, std::ios::binary); boost::archive::binary_oarchive ar(out);
        unsigned int a=1,b=2; ar << a << b << b << a << a << cost; }
      bool rejected = false;
      try { UBODT::read_ubodt_binary(bin, 50000); }
      catch (const std::runtime_error &) { rejected = true; }
      require(rejected == (cost < 0 || !std::isfinite(cost)));
    }
    std::remove(bin.c_str());
    std::cout << "PASS 10 malformed CSV rows, valid CSV, valid/negative/infinite binary cost\n";
    return 0;
  }
  UBODT normal(5003, 20000);
  put(normal,1,3,2,10); put(normal,2,3,3,11);
  auto valid=normal.look_sp_path(1,3);
  require(valid.size()==2 && valid[0]==10 && valid[1]==11);
  require(normal.look_sp_path(1,1).empty());
  require(normal.look_sp_path(8,9).empty());
  UBODT long_path(20029,20000);
  for(int i=0;i<10000;++i) put(long_path,i,10000,i+1,i);
  require(long_path.look_sp_path(0,10000).size()==10000);
  UBODT cycle(5003,100); put(cycle,1,3,2,10); put(cycle,2,3,1,11);
  bool caught=false;
  try { cycle.look_sp_path(1,3); } catch(const std::runtime_error &e) {
    caught=std::string(e.what()).find("cyclic")!=std::string::npos;
  } require(caught);
  UBODT broken(5003,100); put(broken,1,3,2,10); caught=false;
  try { broken.look_sp_path(1,3); } catch(const std::runtime_error &e) {
    caught=std::string(e.what()).find("broken")!=std::string::npos;
  } require(caught);
  if(argc==2) {
    require(UBODT::estimate_ubodt_rows(argv[1])==6199947588LL/36);
    struct stat legacy_stat;
    errno=0;
    const int legacy_rc=stat(argv[1],&legacy_stat);
    const int legacy_errno=errno;
    // Reproduce the original estimator, including its int narrowing and
    // silent -1 return on stat failure. This is NOT the corrected code.
    const long legacy_rows=legacy_rc==0 ? static_cast<int>(legacy_stat.st_size)/36 : -1;
    std::cout << "LEGACY_SIZE_ESTIMATOR stat_rc=" << legacy_rc
              << " errno=" << legacy_errno << " rows=" << legacy_rows
              << " buckets=" << UBODT::find_prime_number(legacy_rows/UBODT::LOAD_FACTOR)
              << " corrected_rows=" << UBODT::estimate_ubodt_rows(argv[1])
              << " corrected_buckets=" << UBODT::find_prime_number(UBODT::estimate_ubodt_rows(argv[1])/UBODT::LOAD_FACTOR)
              << "\n";
  }
  caught=false;
  try { UBODT::estimate_ubodt_rows("nonexistent_ubodt_test_file.txt"); }
  catch(const std::runtime_error &) { caught=true; } require(caught);
  std::cout << "PASS valid, identity, missing, 10000-edge path, cycle, broken, 64-bit size, missing file\n";
}
