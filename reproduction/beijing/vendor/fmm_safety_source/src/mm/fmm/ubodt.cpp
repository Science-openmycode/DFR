//
// Created by Can Yang on 2020/3/22.
//

#include "mm/fmm/ubodt.hpp"
#include "util/util.hpp"

#include <fstream>
#include <stdexcept>
#include <unordered_set>
#include <cmath>
#include <cerrno>
#include <climits>
#include <cctype>
#include <limits>

#include <boost/archive/binary_iarchive.hpp>
#include <boost/format.hpp>

using namespace FMM;
using namespace FMM::CORE;
using namespace FMM::NETWORK;
using namespace FMM::MM;
namespace {
bool parse_record(const char *text, Record &record) {
  unsigned int *fields[] = {&record.source, &record.target, &record.first_n,
                            &record.prev_n, &record.next_e};
  for (auto field : fields) {
    char *end = nullptr;
    errno = 0;
    const long long value = std::strtoll(text, &end, 10);
    if (end == text || errno == ERANGE || value < 0 ||
        static_cast<unsigned long long>(value) >
            std::numeric_limits<unsigned int>::max() || *end != ';') return false;
    *field = static_cast<unsigned int>(value);
    text = end + 1;
  }
  char *end = nullptr;
  errno = 0;
  record.cost = std::strtod(text, &end);
  if (end == text || errno == ERANGE || !std::isfinite(record.cost) ||
      record.cost < 0) return false;
  while (*end && std::isspace(static_cast<unsigned char>(*end))) ++end;
  return *end == '\0';
}
}
UBODT::UBODT(int buckets_arg, int multiplier_arg) :
    buckets(buckets_arg), multiplier(multiplier_arg) {
  SPDLOG_TRACE("Intialization UBODT with buckets {} multiplier {}",
               buckets, multiplier);
  if (buckets <= 0) throw std::runtime_error("Invalid UBODT bucket count");
  hashtable = (Record **) malloc(sizeof(Record *) * buckets);
  if (!hashtable) throw std::bad_alloc();
  for (int i = 0; i < buckets; i++) {
    hashtable[i] = nullptr;
  }
  SPDLOG_TRACE("Intialization UBODT finished");
}

UBODT::~UBODT() {
  /* Clean hashtable */
  SPDLOG_TRACE("Clean UBODT");
  int i;
  for (i = 0; i < buckets; ++i) {
    Record *head = hashtable[i];
    Record *curr;
    while ((curr = head) != nullptr) {
      head = head->next;
      free(curr);
    }
  }
  // Destory hash table pointer
  free(hashtable);
  SPDLOG_TRACE("Clean UBODT finished");
}

Record *UBODT::look_up(NodeIndex source, NodeIndex target) const {
  unsigned int h = cal_bucket_index(source, target);
  Record *r = hashtable[h];
  while (r != nullptr) {
    if (r->source == source && r->target == target) {
      return r;
    } else {
      r = r->next;
    }
  }
  return r;
}

std::vector<EdgeIndex> UBODT::look_sp_path(NodeIndex source,
                                           NodeIndex target) const {
  std::vector<EdgeIndex> edges;
  if (source == target) { return edges; }
  Record *r = look_up(source, target);
  // No transition exist from source to target
  if (r == nullptr) { return edges; }
  std::unordered_set<NodeIndex> visited;
  while (r->first_n != target) {
    if (!visited.insert(r->source).second) {
      throw std::runtime_error("UBODT cyclic next-hop chain: source=" +
          std::to_string(source) + " target=" + std::to_string(target) +
          " repeated=" + std::to_string(r->source));
    }
    edges.push_back(r->next_e);
    r = look_up(r->first_n, target);
    if (r == nullptr) {
      throw std::runtime_error("UBODT broken next-hop chain: source=" +
          std::to_string(source) + " target=" + std::to_string(target));
    }
  }
  edges.push_back(r->next_e);
  return edges;
}

C_Path UBODT::construct_complete_path(int traj_id, const TGOpath &path,
                                      const std::vector<Edge> &edges,
                                      std::vector<int> *indices,
                                      double reverse_tolerance) const {
  C_Path cpath;
  if (!indices->empty()) indices->clear();
  if (path.empty()) return cpath;
  int N = path.size();
  cpath.push_back(path[0]->c->edge->id);
  int current_idx = 0;
  indices->push_back(current_idx);
  SPDLOG_TRACE("Insert index {}", current_idx);
  for (int i = 0; i < N - 1; ++i) {
    const Candidate *a = path[i]->c;
    const Candidate *b = path[i + 1]->c;
    SPDLOG_DEBUG("Check point {} a {} b {}", i, a->edge->id, b->edge->id);
    if ((a->edge->id != b->edge->id) || (a->offset - b->offset >
        a->edge->length * reverse_tolerance)) {
      // segs stores edge index
      auto segs = look_sp_path(a->edge->target, b->edge->source);
      // No transition exist in UBODT
      if (segs.empty() && a->edge->target != b->edge->source) {
        SPDLOG_DEBUG("Edges not found connecting a b");
        SPDLOG_DEBUG("reverse movement {} tolerance {}",
          a->offset - b->offset, a->edge->length * reverse_tolerance);
        SPDLOG_WARN("Traj {} unmatched as edge {} L {} offset {}"
          " and edge {} L {} offset {} disconnected",
          traj_id, a->edge->id, a->edge->length, a->offset,
          b->edge->id, b->edge->length, b->offset);

        indices->clear();
        return C_Path();
      }
      if (segs.empty()) {
        SPDLOG_DEBUG("Edges ab are adjacent");
      } else {
        SPDLOG_DEBUG("Edges connecting ab are {}", segs);
      }
      for (EdgeIndex e:segs) {
        if (static_cast<size_t>(e) >= edges.size()) {
          throw std::runtime_error("UBODT edge index outside the bound network");
        }
        cpath.push_back(edges[e].id);
        ++current_idx;
      }
      cpath.push_back(b->edge->id);
      ++current_idx;
      indices->push_back(current_idx);
      SPDLOG_TRACE("Insert index {}", current_idx);
    } else {
      indices->push_back(current_idx);
      SPDLOG_TRACE("Insert index {}", current_idx);
    }
  }
  return cpath;
}

double UBODT::get_delta() const {
  return delta;
}

unsigned int UBODT::cal_bucket_index(NodeIndex source, NodeIndex target) const {
  return (source * multiplier + target) % buckets;
}


void UBODT::insert(Record *r) {
  //int h = (r->source*multiplier+r->target)%buckets ;
  int h = cal_bucket_index(r->source, r->target);
  r->next = hashtable[h];
  hashtable[h] = r;
  if (r->cost > delta) delta = r->cost;
  ++num_rows;
}

long long UBODT::estimate_ubodt_rows(const std::string &filename) {
  // streamoff is 64-bit on the supported Windows build. Never silently turn
  // a failed size query into a 5003-bucket table for hundreds of millions of rows.
  std::ifstream size_stream(filename, std::ios::binary | std::ios::ate);
  if (!size_stream) throw std::runtime_error("Cannot open UBODT: " + filename);
  const auto end = size_stream.tellg();
  if (end < 0) throw std::runtime_error("Cannot determine UBODT size: " + filename);
  {
    const long long file_bytes = static_cast<long long>(end);
    SPDLOG_INFO("UBODT file size is {} bytes", file_bytes);
    std::string fn_extension = filename.substr(filename.find_last_of(".") + 1);
    std::transform(fn_extension.begin(),
                   fn_extension.end(),
                   fn_extension.begin(),
                   [](unsigned char c) { return std::tolower(c); });
    if (fn_extension == "csv" || fn_extension == "txt") {
      int row_size = 36;
      return file_bytes / row_size;
    } else if (fn_extension == "bin" || fn_extension == "binary") {
      Record r;
      // When exporting to a file using boost binary writer,
      // the padding is removed.
      int row_size = 28;
      return file_bytes / row_size;
    }
  }
  throw std::runtime_error("Unsupported UBODT extension: " + filename);
}

int UBODT::find_prime_number(double value) {
  std::vector<int> prime_numbers = {
      5003, 10039, 20029, 50047, 100669, 200003, 500000,
      1000039, 2000083, 5000101, 10000103, 20000033};
  int N = prime_numbers.size();
  for (int i = 0; i < N; ++i) {
    if (value <= prime_numbers[i]) {
      return prime_numbers[i];
    }
  }
  return prime_numbers[N - 1];
}

std::shared_ptr<UBODT> UBODT::read_ubodt_file(const std::string &filename,
    int multiplier) {
  std::shared_ptr<UBODT> ubodt = nullptr;
  auto start_time = UTIL::get_current_time();
  if (UTIL::check_file_extension(filename,"bin")){
    ubodt = read_ubodt_binary(filename,multiplier);
  } else if (UTIL::check_file_extension(filename,"csv,txt")) {
    ubodt = read_ubodt_csv(filename,multiplier);
  } else {
    std::string message = (boost::format("File format not supported: %1%") % filename).str();
    SPDLOG_CRITICAL(message);
    throw std::runtime_error(message);
  }
  auto end_time = UTIL::get_current_time();
  double duration = UTIL::get_duration(start_time,end_time);
  SPDLOG_INFO("Read UBODT file in {} seconds",duration);
  return ubodt;
}

std::shared_ptr<UBODT> UBODT::read_ubodt_csv(const std::string &filename,
                                             int multiplier) {
  SPDLOG_INFO("Reading UBODT file (CSV format) from {}", filename);
  long long rows = estimate_ubodt_rows(filename);
  int buckets = find_prime_number(rows / LOAD_FACTOR);
  SPDLOG_INFO("Estimated rows {} buckets {}", rows, buckets);
  int progress_step = 1000000;
  std::shared_ptr<UBODT> table = std::make_shared<UBODT>(buckets, multiplier);
  FILE *stream = fopen(filename.c_str(), "r");
  if (!stream) throw std::runtime_error("Cannot read UBODT: " + filename);
  long long NUM_ROWS = 0;
  char line[BUFFER_LINE];
  if (fgets(line, BUFFER_LINE, stream)) {
    SPDLOG_TRACE("Header line skipped.");
  }
  while (fgets(line, BUFFER_LINE, stream)) {
    ++NUM_ROWS;
    Record *r = (Record *) calloc(1, sizeof(Record));
    if (!r) { fclose(stream); throw std::bad_alloc(); }
    /* Parse line into a Record */
    if (!parse_record(line, *r)) {
      free(r); fclose(stream);
      throw std::runtime_error("Invalid UBODT CSV record at data row " + std::to_string(NUM_ROWS));
    }
    r->next = nullptr;
    table->insert(r);
    if (NUM_ROWS % progress_step == 0) {
      SPDLOG_INFO("Read rows {}", NUM_ROWS);
    }
  }
  const bool read_failed = ferror(stream) != 0;
  fclose(stream);
  if (read_failed) throw std::runtime_error("UBODT CSV read failed: " + filename);
  double lf = NUM_ROWS / (double) buckets;
  SPDLOG_INFO("Actual load factor #elements/#tablebuckets {}", lf);
  if (lf > 10) { SPDLOG_WARN("Load factor is too large.") }
  SPDLOG_INFO("Finish reading UBODT with rows {}", NUM_ROWS);
  return table;
}

std::shared_ptr<UBODT> UBODT::read_ubodt_binary(const std::string &filename,
                                                 int multiplier) {
  SPDLOG_INFO("Reading UBODT file (binary format) from {}", filename);
  long long rows = estimate_ubodt_rows(filename);
  int progress_step = 1000000;
  SPDLOG_TRACE("Estimated rows is {}", rows);
  int buckets = find_prime_number(rows / LOAD_FACTOR);
  std::shared_ptr<UBODT> table = std::make_shared<UBODT>(buckets, multiplier);
  long long NUM_ROWS = 0;
  std::ifstream ifs(filename.c_str(), std::ios::binary);
  if (!ifs) throw std::runtime_error("Cannot read UBODT: " + filename);
  // Check byte offset
  std::streampos archiveOffset = ifs.tellg();
  std::streampos streamEnd = ifs.seekg(0, std::ios_base::end).tellg();
  if (archiveOffset < 0 || streamEnd < archiveOffset)
    throw std::runtime_error("Cannot determine UBODT binary size");
  ifs.seekg(archiveOffset);
  boost::archive::binary_iarchive ia(ifs);
  while (ifs.tellg() < streamEnd) {
    ++NUM_ROWS;
    Record *r = (Record *) malloc(sizeof(Record));
    if (!r) throw std::bad_alloc();
    try {
    ia >> r->source;
    ia >> r->target;
    ia >> r->first_n;
    ia >> r->prev_n;
    ia >> r->next_e;
    ia >> r->cost;
    if (!std::isfinite(r->cost) || r->cost < 0)
      throw std::runtime_error("Invalid UBODT binary cost at data row " + std::to_string(NUM_ROWS));
    } catch (...) { free(r); throw; }
    r->next = nullptr;
    table->insert(r);
    if (NUM_ROWS % progress_step == 0) {
      SPDLOG_INFO("Read rows {}", NUM_ROWS);
    }
  }
  ifs.close();
  double lf = NUM_ROWS / (double) buckets;
  SPDLOG_INFO("Actual load factor #elements/#tablebuckets {}", lf);
  if (lf > 10) {
    SPDLOG_WARN("Load factor is too large.")
  }
  SPDLOG_INFO("Finish reading UBODT with rows {}", NUM_ROWS)
  return table;
}
