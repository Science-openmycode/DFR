// Same author core and integration fixes. Grid size is now an explicit CLI input.
#include "PTM.h"
#include <cstdlib>
int main(int argc,char** argv){
 if(argc!=3 || std::atof(argv[1])<=0 || std::atoi(argv[2])<2)return 2;
 PTM ptm;
 ptm.setGridSize(std::atoi(argv[2]));
 ptm.setEpsilon(std::atof(argv[1]));
 ptm.setMaxlevel(3);
 ptm.setEpsPro(0.6);
 ptm.setOutputFile(".\\Data\\synthetic.txt");
 ptm.run();return 0;
}
