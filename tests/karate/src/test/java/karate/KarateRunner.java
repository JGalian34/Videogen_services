package karate;

import com.intuit.karate.junit5.Karate;

/**
 * JUnit 5 runner that discovers and executes all Karate feature files.
 *
 * Usage:
 *   mvn test                           # run all features
 *   mvn test -Dkarate.options="--tags @smoke"  # run only @smoke
 *   mvn test -Dkarate.env=k8s          # target Kubernetes cluster
 */
class KarateRunner {

    @Karate.Test
    Karate testAll() {
        return Karate.run("classpath:features")
                .relativeTo(this);
    }

    @Karate.Test
    Karate testHealth() {
        return Karate.run("classpath:features/health.feature")
                .relativeTo(this);
    }

    @Karate.Test
    Karate testE2E() {
        return Karate.run("classpath:features/e2e_video_pipeline.feature")
                .relativeTo(this);
    }
}

