

 #include "../algorithm/parlayinplaceIntegerSort.hpp"
 #include "../benchmark.hpp"
 #include "../name_extractor.hpp"
 
 using Algorithm = Sequence<true, PLIS::PLIS>;
 
 int main(int argc, char *argv[]) {
     Config config = readParameters(argc, argv, NameExtractor<Algorithm>());
     benchmark<Algorithm>(config);
     return 0;
 }
 