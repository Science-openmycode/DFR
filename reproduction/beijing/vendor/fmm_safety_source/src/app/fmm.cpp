/**
 * Fast map matching.
 *
 * fmm command line program main function
 *
 * @author: Can Yang
 * @version: 2017.11.11
 */

#include "mm/fmm/fmm_app.hpp"
#include <iostream>
#include <exception>

using namespace FMM;
using namespace FMM::MM;
int main(int argc, char **argv){
  try {
  FMMAppConfig config(argc,argv);
  if (config.help_specified) {
    FMMAppConfig::print_help();
    return 0;
  }
  if (!config.validate()){
    return 2;
  }
  FMMApp app(config);
  app.run();
  return 0;
  } catch (const std::exception &error) {
    std::cerr << "FMM_FATAL: " << error.what() << std::endl;
    return 1;
  }
};
