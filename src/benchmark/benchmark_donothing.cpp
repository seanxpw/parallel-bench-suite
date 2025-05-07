

 #include "../algorithm/donothing.hpp"
 #include "../benchmark.hpp"
 #include "../name_extractor.hpp"
 
 using Algorithm = Sequence<true, NOTHING::NOTHING>;
 
 int main(int argc, char *argv[]) {
     Config config = readParameters(argc, argv, NameExtractor<Algorithm>());
     benchmark<Algorithm>(config);
     return 0;
 }
 